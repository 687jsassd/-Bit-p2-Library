from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import Borrow, Book, User
from practical_funcs import remove_html_tags

# 创建borrows蓝图
borrows_bp = Blueprint('borrows', __name__)

# 默认借阅期限（天）
DEFAULT_BORROW_PERIOD = 14

# 借阅图书


@borrows_bp.route('/', methods=['POST'])
@jwt_required()
def borrow_book():
    current_user_id = get_jwt_identity()
    data = request.get_json()

    # 验证必填字段
    if not data or 'book_id' not in data:
        return jsonify({'message': '请提供书籍ID'}), 400

    # 对输入移除HTML标签
    for key in data:
        data[key] = remove_html_tags(str(data[key]))

    book_id = int(data['book_id'])

    try:
        # 检查用户是否存在且状态正常
        user = User.query.filter_by(
            id=current_user_id, deleted_at=None).first()
        if not user:
            return jsonify({'message': '用户不存在或已被删除'}), 404

        if user.status != 0:
            return jsonify({'message': '用户状态异常，无法借阅图书'}), 403

        # 检查图书是否存在且未被删除
        book = Book.query.filter_by(id=book_id, deleted_at=None).first()
        if not book:
            return jsonify({'message': '图书不存在或已被删除'}), 404

        # 检查图书库存
        if book.stock <= 0:
            return jsonify({'message': '图书库存不足'}), 400

        # 检查用户是否已经借阅了这本书
        existing_borrow = Borrow.query.filter_by(
            user_id=current_user_id,
            book_id=book_id,
            status=0,  # 0:借阅中
            deleted_at=None
        ).first()

        if existing_borrow:
            return jsonify({'message': '您已经借阅了这本书'}), 400

        # 创建新的借阅记录
        new_borrow = Borrow()
        new_borrow.user_id = current_user_id
        new_borrow.book_id = book_id
        new_borrow.borrow_time = datetime.now()
        new_borrow.status = 0  # 0:借阅中

        # 减少图书库存
        book.stock -= 1

        db.session.add(new_borrow)
        db.session.commit()

        return jsonify({
            'message': '图书借阅成功',
            'borrow_id': new_borrow.id,
            'book_id': book.id,
            'book_name': book.name,
            'borrow_time': new_borrow.borrow_time.isoformat(),
            'due_time': (new_borrow.borrow_time + timedelta(days=DEFAULT_BORROW_PERIOD)).isoformat()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '图书借阅失败', 'error': str(e)}), 500

# 归还图书


@borrows_bp.route('/<int:borrow_id>/return', methods=['PUT'])
@jwt_required()
def return_book(borrow_id):
    current_user_id = get_jwt_identity()

    try:
        # 查找借阅记录
        borrow = Borrow.query.filter_by(
            id=borrow_id,
            user_id=current_user_id,
            status=0,  # 0:借阅中
            deleted_at=None
        ).first()

        if not borrow:
            return jsonify({'message': '借阅记录不存在或已归还'}), 404

        # 查找图书
        book = Book.query.filter_by(id=borrow.book_id, deleted_at=None).first()
        if not book:
            return jsonify({'message': '图书不存在或已被删除'}), 404

        # 更新借阅记录
        borrow.return_time = datetime.now()
        borrow.status = 1  # 1:已归还
        borrow.updated_at = datetime.now()

        # 增加图书库存
        book.stock += 1

        db.session.commit()

        # 检查是否逾期
        is_overdue = False
        overdue_days = 0
        due_time = borrow.borrow_time + timedelta(days=DEFAULT_BORROW_PERIOD)
        if borrow.return_time > due_time:
            is_overdue = True
            overdue_days = (borrow.return_time - due_time).days

        return jsonify({
            'message': '图书归还成功',
            'borrow_id': borrow.id,
            'book_id': book.id,
            'book_name': book.name,
            'return_time': borrow.return_time.isoformat(),
            'is_overdue': is_overdue,
            'overdue_days': overdue_days
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '图书归还失败', 'error': str(e)}), 500

# 获取当前用户的借阅记录


@borrows_bp.route('/', methods=['GET'])
@jwt_required()
def get_user_borrows():
    current_user_id = get_jwt_identity()

    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # 状态筛选
    status = request.args.get('status', type=int)

    # 构建查询
    query = Borrow.query.filter_by(
        user_id=current_user_id,
        deleted_at=None
    )

    if status is not None and status in [0, 1]:
        query = query.filter_by(status=status)

    borrows = query.order_by(Borrow.borrow_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 构建返回结果
    borrow_list = []
    for borrow in borrows.items:
        book = Book.query.get(borrow.book_id)
        if not book or book.deleted_at:
            continue

        # 计算是否逾期和剩余天数
        is_overdue = False
        days_left = None
        due_time = borrow.borrow_time + timedelta(days=DEFAULT_BORROW_PERIOD)

        if borrow.status == 0:  # 借阅中
            if datetime.now() > due_time:
                is_overdue = True
                days_left = -((datetime.now() - due_time).days)
            else:
                days_left = (due_time - datetime.now()).days

        borrow_list.append({
            'id': borrow.id,
            'book_id': borrow.book_id,
            'book_name': book.name,
            'author': book.author,
            'publisher': book.publisher,
            'borrow_time': borrow.borrow_time.isoformat(),
            'return_time': borrow.return_time.isoformat() if borrow.return_time else None,
            'status': borrow.status,
            'status_text': '借阅中' if borrow.status == 0 else '已归还',
            'due_time': due_time.isoformat(),
            'is_overdue': is_overdue,
            'days_left': days_left
        })

    return jsonify({
        'borrows': borrow_list,
        'total': borrows.total,
        'pages': borrows.pages,
        'current_page': borrows.page
    }), 200

# 获取当前用户的逾期借阅记录


@borrows_bp.route('/overdue', methods=['GET'])
@jwt_required()
def get_overdue_borrows():
    current_user_id = get_jwt_identity()

    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # 查找所有借阅中且已逾期的记录
    now = datetime.now()
    due_time_cutoff = now - timedelta(days=DEFAULT_BORROW_PERIOD)

    borrows = Borrow.query.filter(
        Borrow.user_id == current_user_id,
        Borrow.status == 0,  # 借阅中
        Borrow.borrow_time < due_time_cutoff,
        Borrow.deleted_at == None
    ).order_by(Borrow.borrow_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 构建返回结果
    borrow_list = []
    for borrow in borrows.items:
        book = Book.query.get(borrow.book_id)
        if not book or book.deleted_at:
            continue

        due_time = borrow.borrow_time + timedelta(days=DEFAULT_BORROW_PERIOD)
        overdue_days = (now - due_time).days

        borrow_list.append({
            'id': borrow.id,
            'book_id': borrow.book_id,
            'book_name': book.name,
            'author': book.author,
            'publisher': book.publisher,
            'borrow_time': borrow.borrow_time.isoformat(),
            'due_time': due_time.isoformat(),
            'overdue_days': overdue_days
        })

    return jsonify({
        'overdue_borrows': borrow_list,
        'total': borrows.total,
        'pages': borrows.pages,
        'current_page': borrows.page
    }), 200

# 管理员获取所有借阅记录


@borrows_bp.route('/all', methods=['GET'])
@jwt_required()
def get_all_borrows():
    current_user_id = get_jwt_identity()

    # 检查是否是管理员
    current_user = User.query.get(current_user_id)
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # 筛选参数
    user_id = request.args.get('user_id', type=int)
    book_id = request.args.get('book_id', type=int)
    status = request.args.get('status', type=int)
    is_overdue = request.args.get('is_overdue')

    # 修正
    if is_overdue is not None:
        if is_overdue.lower() == 'true':
            is_overdue = True
        elif is_overdue.lower() == 'false':
            is_overdue = False

    # 构建查询
    query = Borrow.query.filter_by(deleted_at=None)

    if user_id:
        query = query.filter_by(user_id=user_id)
    if book_id:
        query = query.filter_by(book_id=book_id)
    if status is not None and status in [0, 1]:
        query = query.filter_by(status=status)

    # 处理逾期筛选
    if is_overdue is True:
        now = datetime.now()
        due_time_cutoff = now - timedelta(days=DEFAULT_BORROW_PERIOD)
        query = query.filter(
            Borrow.borrow_time < due_time_cutoff
        )

    borrows = query.order_by(Borrow.borrow_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 构建返回结果
    borrow_list = []
    for borrow in borrows.items:
        user = User.query.get(borrow.user_id)
        book = Book.query.get(borrow.book_id)

        if not user or user.deleted_at or not book or book.deleted_at:
            continue

        # 计算是否逾期
        overdue_info = None
        if borrow.status == 0:  # 借阅中
            due_time = borrow.borrow_time + \
                timedelta(days=DEFAULT_BORROW_PERIOD)
            if datetime.now() > due_time:
                overdue_info = {
                    'is_overdue': True,
                    'overdue_days': (datetime.now() - due_time).days,
                    'due_time': due_time.isoformat()
                }
            else:
                overdue_info = {
                    'is_overdue': False,
                    'days_left': (due_time - datetime.now()).days,
                    'due_time': due_time.isoformat()
                }

        borrow_list.append({
            'id': borrow.id,
            'user_id': borrow.user_id,
            'username': user.username,
            'user_name': user.name,
            'book_id': borrow.book_id,
            'book_name': book.name,
            'author': book.author,
            'borrow_time': borrow.borrow_time.isoformat(),
            'return_time': borrow.return_time.isoformat() if borrow.return_time else None,
            'status': borrow.status,
            'status_text': '借阅中' if borrow.status == 0 else '已归还',
            'overdue_info': overdue_info
        })

    return jsonify({
        'borrows': borrow_list,
        'total': borrows.total,
        'pages': borrows.pages,
        'current_page': borrows.page
    }), 200
