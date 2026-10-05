import base64
import string
import random
import hashlib

from Crypto.Cipher import AES

IV = "@@@@&&&&####$$$$"
BLOCK_SIZE = 16

def generate_checksum(param_dict, merchant_key, salt=None):
    params_string = __get_param_string__(param_dict)
    salt = salt if salt else __id_generator__(4)
    final_string = params_string + "|" + salt
    hasher = hashlib.sha256(final_string.encode())
    hash_string = hasher.hexdigest()
    hash_string += salt
    encoded_payload = __encrypt__(hash_string, merchant_key)
    return encoded_payload

def verify_checksum(param_dict, merchant_key, checksum):
    if 'CHECKSUMHASH' in param_dict:
        param_dict.pop('CHECKSUMHASH')
    paytm_hash = __decrypt__(checksum, merchant_key)
    salt = paytm_hash[-4:]
    calculated_checksum = generate_checksum(param_dict, merchant_key, salt)
    return calculated_checksum == checksum

def __id_generator__(size=6, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
    return ''.join(random.choice(chars) for _ in range(size))

def __get_param_string__(params):
    params_string = []
    for key in sorted(params.keys()):
        value = params[key]
        params_string.append("" if value == 'null' else str(value))
    return "|".join(params_string)


def __normalize_key__(key):
    key_bytes = key.encode("utf-8")
    if len(key_bytes) in (16, 24, 32):
        return key_bytes
    if len(key_bytes) < 16:
        return key_bytes.ljust(16, b"\0")
    if len(key_bytes) < 24:
        return key_bytes.ljust(24, b"\0")
    if len(key_bytes) < 32:
        return key_bytes.ljust(32, b"\0")
    return key_bytes[:32]


def __encrypt__(input_string, key):
    pad = lambda s: s + (BLOCK_SIZE - len(s) % BLOCK_SIZE) * chr(BLOCK_SIZE - len(s) % BLOCK_SIZE)
    input_string = pad(input_string)
    cipher = AES.new(__normalize_key__(key), AES.MODE_CBC, IV.encode("utf-8"))
    result = base64.b64encode(cipher.encrypt(input_string.encode("utf-8")))
    return result.decode("utf-8")

def __decrypt__(encrypted_string, key):
    unpad = lambda s: s[0:-ord(s[-1:])]
    cipher = AES.new(__normalize_key__(key), AES.MODE_CBC, IV.encode("utf-8"))
    result = cipher.decrypt(base64.b64decode(encrypted_string.encode("utf-8")))
    return unpad(result).decode("utf-8")