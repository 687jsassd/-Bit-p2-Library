from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, extract, and_, or_
from database import db
from models import Borrow, Book, User

# 创建statistics蓝图
statistics_bp = Blueprint('statistics', __name__)

# 默认借阅期限（天）
DEFAULT_BORROW_PERIOD = 14


# 管理员获取用户借阅报表


@statistics_bp.route('/user/<int:user_id>/reports', methods=['GET'])
@jwt_required()
def get_user_reports(user_id):
    current_user_id = get_jwt_identity()

    # 检查是否是管理员
    current_user = User.query.get(current_user_id)
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 检查用户是否存在
    user = User.query.filter_by(id=user_id, deleted_at=None).first()
    if not user:
        return jsonify({'message': '用户不存在或已被删除'}), 404

    try:
        # 计算总借阅次数
        total_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.user_id == user_id,
            Borrow.deleted_at == None
        ).scalar()

        # 计算已归还次数
        returned_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.user_id == user_id,
            Borrow.status == 1,  # 已归还
            Borrow.deleted_at == None
        ).scalar()

        # 计算逾期次数（已归还且逾期）
        from sqlalchemy import text

        overdue_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.user_id == user_id,
            Borrow.status == 1,  # 已归还
            Borrow.return_time > func.date_add(Borrow.borrow_time, text(
                f'INTERVAL {DEFAULT_BORROW_PERIOD} DAY')),
            Borrow.deleted_at == None
        ).scalar()

        # 计算当前逾期未归还次数
        current_overdue_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.user_id == user_id,
            Borrow.status == 0,  # 借阅中
            Borrow.borrow_time < datetime.now() - timedelta(days=DEFAULT_BORROW_PERIOD),
            Borrow.deleted_at == None
        ).scalar()

        # 计算逾期率
        overdue_rate = 0
        if returned_borrows > 0:
            overdue_rate = round((overdue_borrows / returned_borrows) * 100, 2)

        # 获取用户最近5次借阅记录
        recent_borrows = db.session.query(
            Borrow.id,
            Book.name.label('book_name'),
            Borrow.borrow_time,
            Borrow.return_time,
            Borrow.status
        ).join(Book).filter(
            Borrow.user_id == user_id,
            Borrow.deleted_at == None,
            Book.deleted_at == None
        ).order_by(Borrow.borrow_time.desc()).limit(5).all()

        formatted_recent_borrows = []
        for borrow in recent_borrows:
            # 计算是否逾期
            is_overdue = False
            days_left = None
            due_time = borrow.borrow_time + \
                timedelta(days=DEFAULT_BORROW_PERIOD)

            if borrow.status == 0:  # 借阅中
                if datetime.now() > due_time:
                    is_overdue = True
                    days_left = -((datetime.now() - due_time).days)
                else:
                    days_left = (due_time - datetime.now()).days
            elif borrow.return_time and borrow.return_time > due_time:
                is_overdue = True

            formatted_recent_borrows.append({
                'borrow_id': borrow.id,
                'book_name': borrow.book_name,
                'borrow_time': borrow.borrow_time.isoformat(),
                'return_time': borrow.return_time.isoformat() if borrow.return_time else None,
                'status': borrow.status,
                'status_text': '借阅中' if borrow.status == 0 else '已归还',
                'is_overdue': is_overdue,
                'days_left': days_left
            })

        return jsonify({
            'user_id': user.id,
            'username': user.username,
            'name': user.name,
            'total_borrows': total_borrows,
            'returned_borrows': returned_borrows,
            'overdue_borrows': overdue_borrows + current_overdue_borrows,
            'current_overdue_borrows': current_overdue_borrows,
            'overdue_rate': overdue_rate,
            'recent_borrows': formatted_recent_borrows
        }), 200
    except Exception as e:
        return jsonify({'message': '获取用户报表失败', 'error': str(e)}), 500

# 管理员获取图书借阅报表


@statistics_bp.route('/book/<int:book_id>/reports', methods=['GET'])
@jwt_required()
def get_book_reports(book_id):
    current_user_id = get_jwt_identity()

    # 检查是否是管理员
    current_user = User.query.get(current_user_id)
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 检查图书是否存在
    book = Book.query.filter_by(id=book_id, deleted_at=None).first()
    if not book:
        return jsonify({'message': '图书不存在或已被删除'}), 404

    try:
        # 计算总借阅次数
        total_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.book_id == book_id,
            Borrow.deleted_at == None
        ).scalar()

        # 计算已归还次数
        returned_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.book_id == book_id,
            Borrow.status == 1,  # 已归还
            Borrow.deleted_at == None
        ).scalar()

        # 计算当前借阅中次数
        current_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.book_id == book_id,
            Borrow.status == 0,  # 借阅中
            Borrow.deleted_at == None
        ).scalar()

        # 计算平均借阅时长（天）
        avg_borrow_days = 0
        if returned_borrows > 0:
            result = db.session.query(
                func.avg(func.datediff(Borrow.return_time,
                         Borrow.borrow_time)).label('avg_days')
            ).filter(
                Borrow.book_id == book_id,
                Borrow.status == 1,  # 已归还
                Borrow.deleted_at == None
            ).first()
            if result.avg_days is not None:
                avg_borrow_days = round(float(result.avg_days), 2)

        # 获取最近5次借阅记录
        recent_borrows = db.session.query(
            Borrow.id,
            User.username,
            User.name.label('user_name'),
            Borrow.borrow_time,
            Borrow.return_time,
            Borrow.status
        ).join(User).filter(
            Borrow.book_id == book_id,
            Borrow.deleted_at == None,
            User.deleted_at == None
        ).order_by(Borrow.borrow_time.desc()).limit(5).all()

        formatted_recent_borrows = []
        for borrow in recent_borrows:
            formatted_recent_borrows.append({
                'borrow_id': borrow.id,
                'username': borrow.username,
                'user_name': borrow.user_name,
                'borrow_time': borrow.borrow_time.isoformat(),
                'return_time': borrow.return_time.isoformat() if borrow.return_time else None,
                'status': borrow.status,
                'status_text': '借阅中' if borrow.status == 0 else '已归还'
            })

        # 获取借阅最多的用户（前5名）
        top_borrowers = db.session.query(
            User.id,
            User.username,
            User.name.label('user_name'),
            func.count(Borrow.id).label('borrow_count')
        ).join(User).filter(
            Borrow.book_id == book_id,
            Borrow.deleted_at == None,
            User.deleted_at == None
        ).group_by(User.id).order_by(func.count(Borrow.id).desc()).limit(5).all()

        formatted_top_borrowers = []
        for borrower in top_borrowers:
            formatted_top_borrowers.append({
                'user_id': borrower.id,
                'username': borrower.username,
                'user_name': borrower.user_name,
                'borrow_count': borrower.borrow_count
            })

        return jsonify({
            'book_id': book.id,
            'book_name': book.name,
            'author': book.author,
            'publisher': book.publisher,
            'stock': book.stock,
            'total_borrows': total_borrows,
            'returned_borrows': returned_borrows,
            'current_borrows': current_borrows,
            'avg_borrow_days': avg_borrow_days,
            'recent_borrows': formatted_recent_borrows,
            'top_borrowers': formatted_top_borrowers
        }), 200
    except Exception as e:
        return jsonify({'message': '获取图书报表失败', 'error': str(e)}), 500

# 管理员获取系统整体统计信息


@statistics_bp.route('/system/overview', methods=['GET'])
@jwt_required()
def get_system_overview():
    current_user_id = get_jwt_identity()

    # 检查是否是管理员
    current_user = User.query.get(current_user_id)
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    try:
        # 总用户数（不包括已删除和禁用的）
        total_users = db.session.query(func.count(User.id)).filter(
            User.deleted_at == None,
            User.status == 0  # 正常状态
        ).scalar()

        # 总图书数（不包括已删除的）
        total_books = db.session.query(func.count(Book.id)).filter(
            Book.deleted_at == None
        ).scalar()

        # 总借阅次数
        total_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.deleted_at == None
        ).scalar()

        # 当前借阅中次数
        current_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.status == 0,  # 借阅中
            Borrow.deleted_at == None
        ).scalar()

        # 当前逾期次数
        current_overdue_borrows = db.session.query(func.count(Borrow.id)).filter(
            Borrow.status == 0,  # 借阅中
            Borrow.borrow_time < datetime.now() - timedelta(days=DEFAULT_BORROW_PERIOD),
            Borrow.deleted_at == None
        ).scalar()

        # 热门图书（借阅次数最多的前10本）
        popular_books = db.session.query(
            Book.id,
            Book.name,
            Book.author,
            func.count(Borrow.id).label('borrow_count')
        ).join(Book).filter(
            Borrow.deleted_at == None,
            Book.deleted_at == None
        ).group_by(Book.id).order_by(func.count(Borrow.id).desc()).limit(10).all()

        formatted_popular_books = []
        for book in popular_books:
            formatted_popular_books.append({
                'book_id': book.id,
                'name': book.name,
                'author': book.author,
                'borrow_count': book.borrow_count
            })

        # 活跃用户（借阅次数最多的前10名）
        active_users = db.session.query(
            User.id,
            User.username,
            User.name,
            func.count(Borrow.id).label('borrow_count')
        ).join(User).filter(
            Borrow.deleted_at == None,
            User.deleted_at == None,
            User.status == 0  # 正常状态
        ).group_by(User.id).order_by(func.count(Borrow.id).desc()).limit(10).all()

        formatted_active_users = []
        for user in active_users:
            formatted_active_users.append({
                'user_id': user.id,
                'username': user.username,
                'name': user.name,
                'borrow_count': user.borrow_count
            })

        # 图书分类统计
        category_stats = db.session.query(
            Book.category,
            func.count(Book.id).label('book_count'),
            func.count(Borrow.id).label('borrow_count')
        ).outerjoin(Borrow).filter(
            Book.deleted_at == None,
            or_(Borrow.deleted_at == None, Borrow.id == None)
        ).group_by(Book.category).order_by(func.count(Book.id).desc()).all()

        formatted_category_stats = []
        for category in category_stats:
            formatted_category_stats.append({
                'category': category.category,
                'book_count': category.book_count,
                'borrow_count': category.borrow_count
            })

        return jsonify({
            'total_users': total_users,
            'total_books': total_books,
            'total_borrows': total_borrows,
            'current_borrows': current_borrows,
            'current_overdue_borrows': current_overdue_borrows,
            'popular_books': formatted_popular_books,
            'active_users': formatted_active_users,
            'category_stats': formatted_category_stats
        }), 200
    except Exception as e:
        return jsonify({'message': '获取系统统计信息失败', 'error': str(e)}), 500
