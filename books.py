from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import Book, User
from practical_funcs import remove_html_tags

# 创建books蓝图
books_bp = Blueprint('books', __name__)


# 添加图书
@books_bp.route('/', methods=['POST'])
@jwt_required()
def add_book():
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'message': '请提供图书信息'}), 400

    # 移除HTML标签
    for key in data:
        data[key] = remove_html_tags(data[key])

    # 验证必填字段
    required_fields = ['name', 'author',
                       'publisher', 'category', 'ISBN', 'stock']
    if not all(field in data for field in required_fields):
        return jsonify({'message': '缺少必填字段'}), 400

    # 验证数据格式
    if not data['ISBN'] or len(data['ISBN']) != 13:
        return jsonify({'message': 'ISBN必须是13位'}), 400

    if not isinstance(data['stock'], int) or data['stock'] < 0:
        return jsonify({'message': '库存必须是非负整数'}), 400

    # 检查ISBN是否已存在
    if Book.query.filter_by(ISBN=data['ISBN']).first():
        return jsonify({'message': '该ISBN的图书已存在'}), 400

    # 创建新图书
    new_book = Book()
    new_book.name = data['name']
    new_book.author = data['author']
    new_book.publisher = data['publisher']
    new_book.category = data['category']
    new_book.introduction = data.get('introduction', '')
    new_book.ISBN = data['ISBN']
    new_book.stock = data['stock']

    try:
        db.session.add(new_book)
        db.session.commit()
        return jsonify({'message': '图书添加成功', 'book_id': new_book.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '图书添加失败', 'error': str(e)}), 500

# 获取图书列表


@books_bp.route('/', methods=['GET'])
@jwt_required()
def get_books():
    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # 只获取未删除的图书
    books = Book.query.filter_by(deleted_at=None).paginate(
        page=page, per_page=per_page, error_out=False)

    book_list = []
    for book in books.items:
        book_list.append({
            'id': book.id,
            'name': book.name,
            'author': book.author,
            'publisher': book.publisher,
            'category': book.category,
            'introduction': book.introduction,
            'ISBN': book.ISBN,
            'stock': book.stock,
            'created_at': book.created_at.isoformat() if book.created_at else None,
            'updated_at': book.updated_at.isoformat() if book.updated_at else None
        })

    return jsonify({
        'books': book_list,
        'total': books.total,
        'pages': books.pages,
        'current_page': books.page
    }), 200

# 获取单个图书信息


@books_bp.route('/<int:book_id>', methods=['GET'])
@jwt_required()
def get_book(book_id):
    book = Book.query.filter_by(id=book_id, deleted_at=None).first()

    if not book:
        return jsonify({'message': '图书不存在或已被删除'}), 404

    book_data = {
        'id': book.id,
        'name': book.name,
        'author': book.author,
        'publisher': book.publisher,
        'category': book.category,
        'introduction': book.introduction,
        'ISBN': book.ISBN,
        'stock': book.stock,
        'created_at': book.created_at.isoformat() if book.created_at else None,
        'updated_at': book.updated_at.isoformat() if book.updated_at else None
    }

    return jsonify(book_data), 200

# 更新图书信息


@books_bp.route('/<int:book_id>', methods=['PUT'])
@jwt_required()
def update_book(book_id):
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    book = Book.query.filter_by(id=book_id, deleted_at=None).first()
    if not book:
        return jsonify({'message': '图书不存在或已被删除'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'message': '请提供要更新的图书信息'}), 400

    # 移除HTML标签
    for key in data:
        data[key] = remove_html_tags(data[key])

    # 更新图书信息
    if 'name' in data:
        book.name = data['name']
    if 'author' in data:
        book.author = data['author']
    if 'publisher' in data:
        book.publisher = data['publisher']
    if 'category' in data:
        book.category = data['category']
    if 'introduction' in data:
        book.introduction = data['introduction']
    if 'ISBN' in data:
        # 检查新的ISBN是否已被其他图书使用
        existing_book = Book.query.filter_by(ISBN=data['ISBN']).first()
        if existing_book and existing_book.id != book_id:
            return jsonify({'message': '该ISBN的图书已存在'}), 400
        book.ISBN = data['ISBN']
    if 'stock' in data:
        if not isinstance(data['stock'], int) or data['stock'] < 0:
            return jsonify({'message': '库存必须是非负整数'}), 400
        book.stock = data['stock']

    book.updated_at = datetime.now()

    try:
        db.session.commit()
        return jsonify({'message': '图书信息更新成功'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '图书信息更新失败', 'error': str(e)}), 500

# 删除图书


@books_bp.route('/<int:book_id>', methods=['DELETE'])
@jwt_required()
def delete_book(book_id):
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    book = Book.query.filter_by(id=book_id, deleted_at=None).first()
    if not book:
        return jsonify({'message': '图书不存在或已被删除'}), 404

    try:
        book.soft_delete()
        return jsonify({'message': '图书删除成功'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '图书删除失败', 'error': str(e)}), 500

# 图书搜索


@books_bp.route('/search', methods=['GET'])
@jwt_required()
def search_books():
    # 获取搜索参数
    keyword = request.args.get('keyword', '').strip()
    author = request.args.get('author', '').strip()
    ISBN = request.args.get('ISBN', '').strip()
    category = request.args.get('category', '').strip()

    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # 构建查询
    query = Book.query.filter_by(deleted_at=None)

    if keyword:
        # 按书名模糊搜索
        query = query.filter(Book.name.like(f'%{keyword}%'))
    if author:
        # 按作者模糊搜索
        query = query.filter(Book.author.like(f'%{author}%'))
    if ISBN:
        # 按ISBN精确搜索
        query = query.filter(Book.ISBN == ISBN)
    if category:
        # 按分类精确搜索
        query = query.filter(Book.category == category)

    # 如果没有提供搜索参数，返回空结果
    if not keyword and not author and not ISBN and not category:
        return jsonify({
            'books': [],
            'total': 0,
            'pages': 0,
            'current_page': 1
        }), 200

    books = query.paginate(page=page, per_page=per_page, error_out=False)

    book_list = []
    for book in books.items:
        book_list.append({
            'id': book.id,
            'name': book.name,
            'author': book.author,
            'publisher': book.publisher,
            'category': book.category,
            'introduction': book.introduction,
            'ISBN': book.ISBN,
            'stock': book.stock
        })

    return jsonify({
        'books': book_list,
        'total': books.total,
        'pages': books.pages,
        'current_page': books.page
    }), 200

# 图书分类管理

# 获取所有图书分类


@books_bp.route('/categories', methods=['GET'])
@jwt_required()
def get_categories():
    try:
        # 获取所有唯一的分类
        categories = Book.query.filter_by(deleted_at=None).with_entities(
            Book.category).distinct().all()

        # 转换为列表
        category_list = [category[0] for category in categories]

        return jsonify({
            'categories': category_list,
            'total': len(category_list)
        }), 200
    except Exception as e:
        return jsonify({'message': '获取分类失败', 'error': str(e)}), 500

# 获取指定分类下的图书


@books_bp.route('/categories/<category>', methods=['GET'])
@jwt_required()
def get_books_by_category(category):
    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    books = Book.query.filter_by(category=category, deleted_at=None).paginate(
        page=page, per_page=per_page, error_out=False)

    book_list = []
    for book in books.items:
        book_list.append({
            'id': book.id,
            'name': book.name,
            'author': book.author,
            'publisher': book.publisher,
            'category': book.category,
            'introduction': book.introduction,
            'ISBN': book.ISBN,
            'stock': book.stock
        })

    return jsonify({
        'books': book_list,
        'total': books.total,
        'pages': books.pages,
        'current_page': books.page,
        'category': category
    }), 200

# 重命名分类或者合并分类到其他分类


@books_bp.route('/categories/rename', methods=['PUT'])
@jwt_required()
def rename_category():
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    data = request.get_json()
    if not data or 'old_category' not in data or 'new_category' not in data:
        return jsonify({'message': '请提供旧分类名称和新分类名称'}), 400

    old_category = remove_html_tags(data['old_category'])
    new_category = remove_html_tags(data['new_category'])

    # 检查旧分类是否存在
    if not Book.query.filter_by(category=old_category, deleted_at=None).first():
        return jsonify({'message': '旧分类不存在'}), 404

    try:
        # 更新所有使用该分类的图书
        Book.query.filter_by(category=old_category, deleted_at=None).update({
            'category': new_category,
            'updated_at': datetime.now()
        })
        db.session.commit()

        return jsonify({'message': '分类重命名成功'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '分类重命名失败', 'error': str(e)}), 500
