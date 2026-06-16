def printByteStringAsHex(bytestring):
    for i in range(len(bytestring)):
        print(hex(bytestring[i]), " ", end="")

def bytesToIntBig(bytes_data):
    num_bytes = len(bytes_data)
    signed_int = sum((bytes_data[i] & 0xff) << (8 * (num_bytes - 1 - i)) for i in range(num_bytes))
    signed_int = signed_int if bytes_data[0] & 0x80 == 0 else signed_int - (1 << (8 * num_bytes))
    return signed_int


def reverse_bytes_order(bytes_data):
    num_bytes = len(bytes_data)
    #reverse = bytes(num_bytes)
    reverse = [0] * num_bytes
    for i in range(num_bytes):
        reverse[num_bytes-1-i] = bytes_data[i]
    return bytes(reverse)