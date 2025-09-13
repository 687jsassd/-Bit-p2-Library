from auth import auth_bp
from books import books_bp
from borrows import borrows_bp
from statistics import statistics_bp
from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from models import User, TokenBlacklist
from database import db
import os
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = '123456'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@192.168.200.128:3306/Library_full'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 配置JWT密钥 可改环境变量读
app.config['JWT_SECRET_KEY'] = '123456'

# 初始化扩展
db.init_app(app)
migrate = Migrate(app, db)  # 初始化迁移

# JWT错误处理器

jwt = JWTManager(app)


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'message': '令牌已过期',
        'error': 'token_expired'
    }), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    print("验证令牌时的JWT密钥：", app.config['JWT_SECRET_KEY'])
    print("无效令牌错误详情：", error)  # 关键：打印具体错误原因
    return jsonify({
        'message': '无效的令牌',
        'error': 'invalid_token'
    }), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({
        'message': '缺少访问令牌',
        'error': 'authorization_required'
    }), 401


@jwt.needs_fresh_token_loader
def token_not_fresh_callback(jwt_header, jwt_payload):
    return jsonify({
        'message': '需要新的令牌',
        'error': 'fresh_token_required'
    }), 401


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'message': '令牌已被撤销',
        'error': 'token_revoked'
    }), 401

# 检查令牌是否在黑名单中的回调函数


@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload['jti']  # 获取JWT的唯一标识符
    user_id = jwt_payload.get('sub')  # 获取用户ID
    issued_at = datetime.fromtimestamp(jwt_payload.get('iat'))  # 获取令牌签发时间

    try:
        # 检查令牌是否在黑名单中
        token = TokenBlacklist.query.filter_by(jti=jti).first()
        if token is not None:
            return True

        # 检查用户密码是否已修改
        if user_id:
            user = User.query.get(user_id)
            if user:
                # 确保 issued_at 是 UTC 时间格式
                if issued_at.tzinfo is None:
                    issued_at = issued_at.replace(tzinfo=timezone.utc)

                # 确保 password_updated_at 是 UTC 时间格式
                if user.password_updated_at.tzinfo is None:
                    password_updated_at_utc = user.password_updated_at.replace(
                        tzinfo=timezone.utc)
                else:
                    password_updated_at_utc = user.password_updated_at

                if password_updated_at_utc > issued_at:
                    # 密码已修改，令牌失效
                    print(f"用户 {user_id} 的密码已修改，令牌失效")
                    return True
        return False
    except Exception as e:
        print(f"检查令牌黑名单时出错: {str(e)}")
        return False


# 注册蓝图
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(books_bp, url_prefix='/api/books')
app.register_blueprint(borrows_bp, url_prefix='/api/borrows')
app.register_blueprint(statistics_bp, url_prefix='/api/statistics')


@app.route('/')
def index():
    user = User.query.first()
    return f"第一个用户: {user.username if user else '无'}"


if __name__ == '__main__':
    app.run(debug=True)
