# 检查字符串是否已经是Werkzeug哈希格式
def is_werkzeug_hash(password_str):
    # Werkzeug生成的哈希格式通常为：pbkdf2:sha256:<iterations>$<salt>$<hash> 或 scrypt:32768:8:1$...
    if not password_str or not isinstance(password_str, str):
        return False
    return password_str.startswith('pbkdf2:sha256:') or password_str.startswith('scrypt:')

# 对用户信息的输入data(json)的部分字段的合法性校验


def is_valid_user_data(data):
    import re
    # 用户名存在则进行长度校验
    if 'username' in data and (len(data['username']) < 6 or len(data['username']) > 20):
        return False
    # 邮箱存在则进行格式校验
    if 'email' in data and not re.match(r'^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z0-9]{2,6}$', data['email']):
        return False
    # 手机号存在则进行格式校验
    if 'phone' in data and not re.match(r'^1[3-9]\d{9}$', data['phone']):
        return False
    return True

# 对输入移除HTML标签


def remove_html_tags(text):
    import re
    if not text or not isinstance(text, str):
        return text
    # 移除HTML标签
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)
