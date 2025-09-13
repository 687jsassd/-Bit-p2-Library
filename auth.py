from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import (create_access_token, create_refresh_token,
                                jwt_required, get_jwt_identity, get_jwt)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from database import db
from models import User, TokenBlacklist
from practical_funcs import is_valid_user_data, remove_html_tags

# 创建auth蓝图
auth_bp = Blueprint('auth', __name__)

# 配置JWT过期时间
ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
REFRESH_TOKEN_EXPIRES = timedelta(days=7)


# 共用函数


def check_user_exists(username=None, email=None, phone=None):
    # 检查用户及信息是否存在,输入的参数可以是用户名、邮箱、手机号，允许空；
    # 如果存在，返回错误信息，否则返回None
    if username and User.query.filter_by(username=username).first():
        return jsonify({'message': '用户名已存在'}), 400
    if email and User.query.filter_by(email=email).first():
        return jsonify({'message': '邮箱已存在'}), 400
    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({'message': '手机号已存在'}), 400
    return None

# 用户注册接口


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    # 对输入移除HTML标签
    for key in data:
        data[key] = remove_html_tags(data[key])

    # 验证必填字段
    required_fields = ['username', 'email', 'phone', 'password', 'name', 'sex']
    if not all(field in data for field in required_fields):
        return jsonify({'message': '缺少必填字段'}), 400

    # 格式校验
    if not is_valid_user_data(data):
        return jsonify({'message': '输入数据格式错误'}), 400

    # 检查用户是否已存在
    user_exists = check_user_exists(
        username=data['username'], email=data['email'], phone=data['phone'])
    if user_exists:
        return user_exists

    # 创建新用户
    hashed_password = generate_password_hash(data['password'])
    new_user = User()
    new_user.username = data['username']
    new_user.email = data['email']
    new_user.phone = data['phone']
    new_user.password = hashed_password
    new_user.name = data['name'] if data['name'] is not None else '不知名'
    new_user.sex = data['sex'] if data['sex'] in [0, 1, 2] else 2
    new_user.age = data.get('age') if data.get('age') is not None else 0
    new_user.introduction = data.get('introduction') if data.get(
        'introduction') is not None else '未添加简介'
    new_user.privilege = 0  # 默认为普通用户,不可以注册时添加此字段
    new_user.status = 0

    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'message': '注册成功'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '注册失败', 'error': str(e)}), 500

# 用户登录接口


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    # 对输入移除HTML标签
    for key in data:
        data[key] = remove_html_tags(data[key])
    # 用户名格式校验(为了保证性能，不采用is_vaild_user_data，避免输入数据恶意添加有phone等无关数据导致性能占用)
    if 'username' in data and (len(data['username']) < 6 or len(data['username']) > 20):
        return jsonify({'message': '用户名长度必须在6-20之间'}), 400

    # 验证必填字段
    if not data or 'password' not in data:
        return jsonify({'message': '请提供登录凭据和密码'}), 400

    # 支持用户名、邮箱或手机号登录
    user = None
    if 'username' in data:
        user = User.query.filter_by(username=data['username']).first()
    elif 'email' in data:
        user = User.query.filter_by(email=data['email']).first()
    elif 'phone' in data:
        user = User.query.filter_by(phone=data['phone']).first()
    else:
        return jsonify({'message': '请提供用户名、邮箱或手机号作为登录凭据'}), 400

    # 验证用户和密码
    if not user or not check_password_hash(user.password, data['password']):
        return jsonify({'message': '用户名或密码错误'}), 401

    # 检查用户状态
    if user.status == 1:
        return jsonify({'message': '用户已被禁用'}), 401

    # 生成令牌
    access_token = create_access_token(
        identity=str(user.id), expires_delta=ACCESS_TOKEN_EXPIRES)
    refresh_token = create_refresh_token(
        identity=str(user.id), expires_delta=REFRESH_TOKEN_EXPIRES)

    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user_id': user.id,
        'privilege': user.privilege
    }), 200

# 刷新令牌接口


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    current_user_id = get_jwt_identity()
    jwt_data = get_jwt()
    current_jti = jwt_data['jti']
    expires_at = datetime.fromtimestamp(jwt_data['exp'])

    # 将当前刷新令牌添加到黑名单
    revoked_token = TokenBlacklist()
    revoked_token.jti = current_jti
    revoked_token.token_type = 'refresh'
    revoked_token.user_id = current_user_id
    revoked_token.expires_at = expires_at

    try:
        db.session.add(revoked_token)

        # 生成新的访问令牌和刷新令牌
        new_access_token = create_access_token(
            identity=str(current_user_id), expires_delta=ACCESS_TOKEN_EXPIRES)
        new_refresh_token = create_refresh_token(
            identity=str(current_user_id), expires_delta=REFRESH_TOKEN_EXPIRES)

        db.session.commit()

        return jsonify({
            'access_token': new_access_token,
            'refresh_token': new_refresh_token
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '刷新令牌失败', 'error': str(e)}), 500

# 获取当前用户信息


@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    current_user_id = get_jwt_identity()
    user = User.query.filter_by(
        id=current_user_id).filter_by(deleted_at=None).first()

    if not user:
        return jsonify({'message': '用户不存在或已被修改或删除'}), 404

    # 返回用户信息（不包含密码等敏感信息）
    user_data = {
        'username': user.username,
        'email': user.email,
        'phone': user.phone,
        'name': user.name,
        'sex': user.sex,
        'age': user.age,
        'introduction': user.introduction,
    }

    return jsonify(user_data), 200

# 修改用户信息


@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity()
    user = User.query.filter_by(
        id=current_user_id).filter_by(deleted_at=None).first()
    data = request.get_json()

    if not user:
        return jsonify({'message': '用户不存在或已被修改或删除'}), 404

    if not data:
        return jsonify({'message': '请提供要更新的信息'}), 400
    # 对输入移除HTML标签
    for key in data:
        data[key] = remove_html_tags(data[key])

    # 更新用户信息
    if 'name' in data:
        user.name = data['name']
    if 'sex' in data and data['sex'] in [0, 1, 2]:
        user.sex = data['sex']
    if 'age' in data and data['age'] > 0 and data['age'] < 120:
        user.age = data['age']
    if 'introduction' in data:
        user.introduction = data['introduction']

    try:
        db.session.commit()
        return jsonify({'message': '信息更新成功'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '信息更新失败', 'error': str(e)}), 500

# 检查用户名是否可用


@auth_bp.route('/check_username/<username>', methods=['GET'])
def check_username(username):
    user = User.query.filter_by(username=username).first()
    if user:
        return jsonify({'available': False}), 200
    return jsonify({'available': True}), 200

# 检查邮箱是否可用


@auth_bp.route('/check_email/<email>', methods=['GET'])
def check_email(email):
    user = User.query.filter_by(email=email).first()
    if user:
        return jsonify({'available': False}), 200
    return jsonify({'available': True}), 200

# 检查手机号是否可用


@auth_bp.route('/check_phone/<phone>', methods=['GET'])
def check_phone(phone):
    user = User.query.filter_by(phone=phone).first()
    if user:
        return jsonify({'available': False}), 200
    return jsonify({'available': True}), 200

# 管理员获取用户列表


@auth_bp.route('/users', methods=['GET'])
@jwt_required()
def get_users():
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    users = User.query.filter_by(deleted_at=None).paginate(
        page=page, per_page=per_page, error_out=False)

    user_list = []
    for user in users.items:
        user_list.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'phone': user.phone,
            'name': user.name,
            'sex': user.sex,
            'age': user.age,
            'privilege': user.privilege,
            'status': user.status,
            'introduction': user.introduction,
            'created_at': user.created_at.isoformat() if user.created_at else None
        })

    return jsonify({
        'users': user_list,
        'total': users.total,
        'pages': users.pages,
        'current_page': users.page
    }), 200

# 修改用户权限


@auth_bp.route('/users/<int:user_id>/privilege', methods=['PUT'])
@jwt_required()
def update_user_privilege(user_id):
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 检查是否试图修改自己的权限
    if int(current_user_id) == user_id:
        return jsonify({'message': '管理员不能修改自己的权限'}), 403

    # 检查目标用户是否存在
    target_user = User.query.filter_by(id=user_id, deleted_at=None).first()
    if not target_user:
        return jsonify({'message': '目标用户不存在'}), 404

    # 获取请求数据
    data = request.get_json()
    if not data or 'privilege' not in data:
        return jsonify({'message': '请提供新的权限等级'}), 400

    # 验证权限等级是否有效
    new_privilege = data['privilege']
    if new_privilege not in [0, 1]:
        return jsonify({'message': '权限等级必须是0或1'}), 400

    try:
        # 更新用户权限
        target_user.privilege = new_privilege
        target_user.updated_at = datetime.now()
        db.session.commit()

        return jsonify({
            'message': '用户权限修改成功',
            'user_id': target_user.id,
            'new_privilege': target_user.privilege
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '用户权限修改失败', 'error': str(e)}), 500

# 管理员软删除普通用户


@auth_bp.route('/users/<int:user_id>/soft_delete', methods=['PUT'])
@jwt_required()
def soft_delete_user(user_id):
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 检查是否试图删除自己
    if int(current_user_id) == user_id:
        return jsonify({'message': '管理员不能删除自己'}), 403

    # 检查目标用户是否存在且未被删除
    target_user = User.query.filter_by(id=user_id, deleted_at=None).first()
    if not target_user:
        return jsonify({'message': '目标用户不存在或已被删除'}), 404

    # 检查是否试图删除另一个管理员
    if target_user.privilege == 1:
        return jsonify({'message': '不能删除其他管理员'}), 403

    try:
        # 软删除用户
        target_user.deleted_at = datetime.now()
        target_user.updated_at = datetime.now()
        db.session.commit()

        return jsonify({
            'message': '用户已软删除',
            'user_id': target_user.id
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '用户删除失败', 'error': str(e)}), 500

# 管理员封禁普通用户


@auth_bp.route('/users/<int:user_id>/ban', methods=['PUT'])
@jwt_required()
def ban_user(user_id):
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 检查是否试图封禁自己
    if int(current_user_id) == user_id:
        return jsonify({'message': '管理员不能封禁自己'}), 403

    # 检查目标用户是否存在且未被删除
    target_user = User.query.filter_by(id=user_id, deleted_at=None).first()
    if not target_user:
        return jsonify({'message': '目标用户不存在或已被删除'}), 404

    # 检查是否试图封禁另一个管理员
    if target_user.privilege == 1:
        return jsonify({'message': '不能封禁其他管理员'}), 403

    # 检查用户是否已经被封禁
    if target_user.status == 1:
        return jsonify({'message': '用户已经被封禁'}), 400

    try:
        # 封禁用户
        target_user.status = 1
        target_user.updated_at = datetime.now()
        db.session.commit()

        return jsonify({
            'message': '用户已封禁',
            'user_id': target_user.id
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '用户封禁失败', 'error': str(e)}), 500

# 管理员解封普通用户


@auth_bp.route('/users/<int:user_id>/unban', methods=['PUT'])
@jwt_required()
def unban_user(user_id):
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    # 检查是否是管理员
    if not current_user or current_user.privilege != 1:
        return jsonify({'message': '权限不足'}), 403

    # 检查目标用户是否存在且未被删除
    target_user = User.query.filter_by(id=user_id, deleted_at=None).first()
    if not target_user:
        return jsonify({'message': '目标用户不存在或已被删除'}), 404

    # 检查是否试图解封另一个管理员
    if target_user.privilege == 1:
        return jsonify({'message': '不能解封其他管理员'}), 403

    # 检查用户是否已经是正常状态
    if target_user.status == 0:
        return jsonify({'message': '用户已经是正常状态'}), 400

    try:
        # 解封用户
        target_user.status = 0
        target_user.updated_at = datetime.now()
        db.session.commit()

        return jsonify({
            'message': '用户已解封',
            'user_id': target_user.id
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '用户解封失败', 'error': str(e)}), 500


@auth_bp.route('/change_password', methods=['POST'])
@jwt_required()
def change_password():
    current_user_id = get_jwt_identity()
    user = User.query.filter_by(
        id=current_user_id).filter_by(deleted_at=None).first()

    if not user:
        return jsonify({'message': '用户不存在'}), 404

    data = request.get_json()
    if not data or 'current_password' not in data or 'new_password' not in data:
        return jsonify({'message': '请提供当前密码和新密码'}), 400

    # 验证当前密码
    if not check_password_hash(user.password, data['current_password']):
        return jsonify({'message': '当前密码错误'}), 401

    try:
        # 修改密码
        user.password = generate_password_hash(data['new_password'])
        user.password_updated_at = datetime.now()
        db.session.commit()
        return jsonify({'message': '密码修改成功，请重新登录'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': '密码修改失败', 'error': str(e)}), 500
