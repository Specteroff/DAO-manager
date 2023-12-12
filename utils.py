import socket, datetime, hashlib, string, random, pickle
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization


class Proposal:
    def __init__(self, org_id, content, start, end):
        self.org_id = org_id
        self.content = content
        self.start = start
        self.end = end

    def info(self):
        return str(str(self.content) + ' was started at ' + str(self.start) + ' and it ends at '
                   + str(self.end) + ' in organization ' + str(self.org_id))

    def expired(self):
        return datetime.datetime.now() > self.end


def get_ip():
    hostname = socket.gethostname()
    return socket.gethostbyname(hostname)


def encodeSHA256(data):
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def gen_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())


def gen_public_key(sk):
    return sk.public_key()


def sign(sk, message):
    return sk.sign(message.encode('utf-8'), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())


def verify(signature, pk, message):
    try:
        pk.verify(signature, message.encode('utf-8'), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    except:
        return False
    return True


def remove_if_have(list, element):
    if element in list:
        list.remove(element)


def encode_vote_info(org_id, proposal, voter, vote):
    return str(org_id) + '|' + proposal + '|' + voter + '|' + vote


def validate_signature(signature, pk, org_id, proposal, voter, vote):
    return verify(signature, pk, encode_vote_info(org_id, proposal, voter, vote))


def generate_random_string():
    size = random.randint(1, 50)
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for i in range(size))


def serialize_key(key):
    return key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)


def deserialize_key(serialized_key):
    return serialization.load_pem_public_key(serialized_key, backend=default_backend())
