import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import os


# Set environment with your own password
needle_pwd = os.getenv('needle_pwd')


def sha256_encode(data):
    hash_object = hashlib.sha256()
    hash_object.update(data.encode('utf-8'))
    hex_dig = hash_object.hexdigest()
    return hex_dig


def hash_key(key_str):
    hash_object = hashlib.sha256()
    hash_object.update(key_str.encode())
    return hash_object.digest()[:32]


def encrypt(plain_text, key_str=needle_pwd):
    key = hash_key(key_str)
    backend = default_backend()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(plain_text.encode()) + padder.finalize()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    return (iv + encrypted_data).hex()


def decrypt(cipher_text_hex, key_str=needle_pwd):
    key = hash_key(key_str)
    backend = default_backend()
    cipher_text = bytes.fromhex(cipher_text_hex)
    iv = cipher_text[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    decryptor = cipher.decryptor()
    decrypted_padded_data = decryptor.update(cipher_text[16:]) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    original_data = unpadder.update(decrypted_padded_data) + unpadder.finalize()
    return original_data.decode()


if __name__ == '__main__':
    import random
    import string

    # u ^ rk * uLxmQ7yBMJc
    def generate_password(length=16):
        # 定义密码字符集，包括字母、数字和符号
        chars = string.ascii_letters + string.digits + '*#$@^'
        # 从字符集中随机选择字符以生成密码
        password = ''.join(random.choice(chars) for _ in range(length))
        return password


    # 生成一个长度为16的随机密码
    random_password = generate_password()
    # print("Generated password:", random_password)
    #
    # cipher_text = encrypt('needle_product_search', random_password)  # Replace it with the text you need to encrypt
    # print(cipher_text)
    # plain_text = decrypt(cipher_text)
    # print(plain_text)

    # hash_value = sha256_encode("u^rk*uLxmQ7yBMJc")
    hash_value = sha256_encode("needle_product_search")# Replace it with the text you need to encode
    print(hash_value)
