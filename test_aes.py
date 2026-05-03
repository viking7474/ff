from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import json

data = {
    "browser.profileName": "hoadeptrai",
    "showcursor": False,
    "battery:charging": False,
    "battery:level": 0.55
}

json_str = json.dumps(data)

key = b"CamoufoxSecretKeyForAES256Cipher"
iv = b"0123456789ABCDEF"

cipher = AES.new(key, AES.MODE_CBC, iv)
padded_data = pad(json_str.encode('utf-8'), AES.block_size)
ciphertext = cipher.encrypt(padded_data)
hex_str = binascii.hexlify(ciphertext).decode('utf-8')

print("Encrypted Hex String to pass to CAMOU_CONFIG:")
print(hex_str)
