# models.py
from database import db
from datetime import datetime, timezone
# 时间戳mixin类


class TimestampMixin:
    created_at = db.Column(
        # 创建时间
        db.DateTime, default=datetime.now(), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(),
                           # 更新时间
                           onupdate=datetime.now(), nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)  # 软删除标记

# 用户信息表


class User(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)  # 主键
    # 权限相关部分
    username = db.Column(db.String(80), unique=True, nullable=False)  # 用户名
    email = db.Column(db.String(120), unique=True, nullable=False)  # 邮箱
    phone = db.Column(db.String(11), unique=True, nullable=False)  # 手机号
    password = db.Column(db.String(255), nullable=False)  # 密码(哈希后)
    password_updated_at = db.Column(
        # 密码更新时间
        db.DateTime, default=datetime.now(), nullable=False)
    privilege = db.Column(db.Integer, nullable=False,
                          default=0)  # 权限等级(0:普通用户, 1:管理员)
    status = db.Column(db.Integer, nullable=False, default=0)  # 状态(0:正常,1:禁用)
    # 个人信息部分
    name = db.Column(db.String(16), nullable=False)  # 姓名
    sex = db.Column(db.Integer, nullable=False)  # 性别(0:男,1:女,2:未知)
    age = db.Column(db.Integer)  # 年龄
    introduction = db.Column(db.String(200))  # 简介

    # 索引
    __table_args__ = (
        db.Index('idx_user_username', 'username'),
        db.Index('idx_user_email', 'email'),
        db.Index('idx_user_phone', 'phone'),
    )

    def soft_delete(self):
        self.deleted_at = datetime.now()
        db.session.commit()

    def __repr__(self):
        return f'<User {self.username}>'

# 书籍信息表


class Book(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)  # 主键
    name = db.Column(db.String(120), nullable=False)  # 书名
    author = db.Column(db.String(80), nullable=False)  # 作者
    publisher = db.Column(db.String(80), nullable=False)  # 出版社
    category = db.Column(db.String(80), nullable=False)  # 分类
    introduction = db.Column(db.String(200))  # 简介
    ISBN = db.Column(db.String(13), unique=True, nullable=False)  # ISBN
    stock = db.Column(db.Integer, nullable=False)  # 库存

    # 索引
    __table_args__ = (
        db.Index('idx_book_name', 'name'),
        db.Index('idx_book_author', 'author'),
        db.Index('idx_book_publisher', 'publisher'),
        db.Index('idx_book_ISBN', 'ISBN'),
        db.Index('idx_book_category', 'category'),
    )

    def soft_delete(self):
        self.deleted_at = datetime.now()
        db.session.commit()

    def __repr__(self):
        return f'<Book {self.name}>'

# 借阅信息表


class Borrow(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)  # 主键
    user_id = db.Column(db.Integer, db.ForeignKey(
        'user.id'), nullable=False)  # 用户ID
    book_id = db.Column(db.Integer, db.ForeignKey(
        'book.id'), nullable=False)  # 书籍ID
    borrow_time = db.Column(db.DateTime, nullable=False)  # 借阅时间
    return_time = db.Column(db.DateTime, nullable=True)  # 归还时间
    # 外键关联
    user = db.relationship('User', backref=db.backref('borrows', lazy=True))
    book = db.relationship('Book', backref=db.backref('borrows', lazy=True))
    # 状态字段
    status = db.Column(db.Integer, nullable=False,
                       default=0)  # 状态(0:借阅中, 1:已归还)
    # 索引
    __table_args__ = (
        db.Index('idx_borrow_user_id', 'user_id'),
        db.Index('idx_borrow_book_id', 'book_id'),
        db.Index('idx_borrow_status', 'status'),
    )

    def soft_delete(self):
        self.deleted_at = datetime.now()
        db.session.commit()

    def __repr__(self):
        return f'<Borrow {self.id}>'


class TokenBlacklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)  # JWT的唯一标识符
    # 令牌类型（access或refresh）
    token_type = db.Column(db.String(10), nullable=False)
    user_id = db.Column(db.Integer, nullable=False, index=True)  # 关联的用户ID
    revoked_at = db.Column(db.DateTime, nullable=False,
                           default=datetime.now())  # 撤销时间
    expires_at = db.Column(db.DateTime, nullable=False)  # 令牌过期时间

    def __repr__(self):
        return f'<TokenBlacklist jti={self.jti} user_id={self.user_id}>'
