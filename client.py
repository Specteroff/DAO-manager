import socket, pickle, threading, sys, datetime, time, random
from utils import *

PRIVATE_KEY = gen_private_key()
PUBLIC_KEY = gen_public_key(PRIVATE_KEY)
notifications = []
LISTEN_NEIGHBOURS_PORT = 12345
SEND_NEIGHBOUR_PORT = 12345
SEND_SERVER_PORT = 12346
LISTEN_SERVER_PORT = 12347
SELF_IP = get_ip()
ZERO_COUNT = 2
TRANSACTIONS_IN_BLOCK = 1


class Transaction:
    def __init__(self, org_id, proposal, voter, vote, signature):
        self.org_id = org_id
        self.proposal = proposal
        self.voter = voter
        self.vote = vote
        self.signature = signature

    def string_form(self):
        return encode_vote_info(self.org_id, self.proposal, self.voter, self.vote) + '|' + str(self.signature)

    def string_form_to_check_copies(self):
        return str(self.org_id) + '|' + self.proposal + '|' + self.voter


class Block:
    def __init__(self, prev_hash, transactions, PoW):
        self.transactions = transactions
        self.PoW = PoW
        self.prev_hash = prev_hash

    def count(self, proposal):
        approval_level = 0
        for transaction in self.transactions:
            if transaction.vote == 'Y':
                approval_level += query_coeff(transaction.org_id, transaction.voter)
            elif transaction.vote == 'N':
                approval_level -= query_coeff(transaction.org_id, transaction.voter)
        return approval_level

    def get_s(self): # without PoW
        s = ''
        for transaction in self.transactions:
            s += transaction.string_form()
        s += self.prev_hash
        return s

    def get_hash(self):
        return encodeSHA256(self.get_s() + self.PoW)

    def verify(self):
        return self.get_hash().startswith('0' * ZERO_COUNT)

    def print(self, file):
        for i, transaction in enumerate(self.transactions):
            file.write('Transaction #' + str(i + 1) + ': in proposal ' + transaction.proposal + ' ' + transaction.voter
                  + ' voted for ' + transaction.vote + '\n')


class BlockChain:
    def __init__(self):
        self.blocks = []

    def get_result(self, proposal):
        approval_level = 0
        for block in self.blocks:
            approval_level += block.count(proposal)
        return 'accepted' if approval_level > 0 else 'not accepted'

    def verify(self, org_id):
        ok = True
        counted_transactions = set()
        for i, block in enumerate(self.blocks):
            ok &= block.verify()
            if i != 0:
                ok &= (block.prev_hash == self.blocks[i - 1].get_hash())
            for transaction in block.transactions:
                ok &= transaction not in counted_transactions
                counted_transactions.add(transaction.string_form_to_check_copies())
        ok &= counted_transactions == set(organizations[org_id].visited_transactions)
        if ok:
            print('Blockchain verified')
        return ok

    def size(self):
        return len(self.blocks)

    def print(self, org_id):
        with open('blockchain' + str(org_id) + '.txt', 'w') as file:
            file.write('Currently blockchain has ' + str(len(self.blocks)) + ' blocks in it\n\n')
            for i, block in enumerate(self.blocks):
                file.write('Block #' + str(i + 1) + ':\n')
                block.print(file)
                file.write('\nHash of this block is ' + block.get_hash())
                file.write('\nAnd the nonce is ' + block.PoW)
                file.write('\n\n')


class OrgInfo:
    def __init__(self):
        self.neighbours = []
        self.blockchain = BlockChain()
        self.proposals = []
        self.transaction_pool = []
        self.visited_transactions = []

    def set_neighbours(self, neighbours):
        self.neighbours = neighbours


organizations = {}
current_chain = BlockChain()


class ListenNeighbours(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.s = None

    def run(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind((SELF_IP, LISTEN_NEIGHBOURS_PORT))
        self.s.listen(10)
        while True:
            n_s, n_addr = self.s.accept()
            query_encoded = n_s.recv(4096)
            query = pickle.loads(query_encoded)
            req = query[0]
            if req == 'exit':
                break
            elif req == 'Add neighbour':
                org_id = int(query[1])
                organizations[org_id].neighbours.append(n_addr[0])
                print('Neigbhour ' + n_addr[0] + ' added')
            elif req == 'Vote':
                transaction = query[1]
                pk = deserialize_key(query[2])
                if validate_signature(transaction.signature, pk, transaction.org_id, transaction.proposal, transaction.voter,
                            transaction.vote) and transaction.string_form_to_check_copies() not in organizations[transaction.org_id].visited_transactions:
                    print(n_addr[0] + ' wants to vote')
                    organizations[transaction.org_id].visited_transactions.append(transaction.string_form_to_check_copies())
                    organizations[transaction.org_id].transaction_pool.append(transaction)
                    for neighbour in organizations[transaction.org_id].neighbours:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect((neighbour, SEND_NEIGHBOUR_PORT))
                        s.send(pickle.dumps(query))
                        s.close()
            elif req == 'Suggest blockchain':
                org_id = query[1]
                blockchain = query[2]
                transaction_pool = query[3]
                print(n_addr[0] + ' wants to suggest a blockhain')
                if organizations[org_id].blockchain.size() <= blockchain.size() and blockchain.verify(org_id):
                    print('accepted blockchain')
                    miner.stop()
                    organizations[org_id].blockchain = blockchain
                    organizations[org_id].transaction_pool = transaction_pool
                    for neighbour in organizations[org_id].neighbours:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect((neighbour, SEND_NEIGHBOUR_PORT))
                        s.send(pickle.dumps(query))
                        s.close()
                    miner.resume()
                else:
                    print('rejected blockchain')
        self.s.close()


class ListenServer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.s = None

    def run(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind((SELF_IP, LISTEN_SERVER_PORT))
        self.s.listen(10)
        while True:
            n_s, n_addr = self.s.accept()
            query_encoded = n_s.recv(1024)
            query = pickle.loads(query_encoded)
            req = query[0]
            if req == 'exit':
                break
            elif req == 'New proposal':
                org_id = query[1]
                content = query[2]
                start = query[3]
                end = query[4]
                new_proposal = Proposal(org_id, content, start, end)
                notifications.append('New proposal: ' + new_proposal.info())
                organizations[org_id].proposals.append(new_proposal)
                print('New notification. In total you have ' + str(len(notifications)) + ' notifications')
            n_s.close()
        self.s.close()


class ProposalAccountant(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.terminated = False

    def run(self):
        while not self.terminated:
            time.sleep(0.5)
            for org_id in organizations.keys():
                to_del = []
                for proposal in organizations[org_id].proposals:
                    if proposal.expired():
                        notifications.append('Proposal ' + proposal.content + ' ended in organization ' + str(proposal.org_id) +
                              '. The result is: ' + organizations[proposal.org_id].blockchain.get_result(proposal.content))
                        print('New notification. In total you have ' + str(len(notifications)) + ' notifications')
                        to_del.append(proposal)
                for proposal in to_del:
                    organizations[org_id].proposals.remove(proposal)

    def terminate(self):
        self.terminated = True


class Miner(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.terminated = False
        self.stopped = False

    def run(self):
        while not self.terminated:
            time.sleep(0.1)
            if not self.stopped and not len(organizations) == 0:
                org_id = list(organizations.keys())[random.randint(0, len(organizations) - 1)]
                if len(organizations[org_id].transaction_pool) >= TRANSACTIONS_IN_BLOCK:
                    print('Trying to mine a new block')
                    nonce = generate_random_string()
                    s = ''
                    # random.shuffle(organizations[org_id].transaction_pool)
                    for transaction in organizations[org_id].transaction_pool[:TRANSACTIONS_IN_BLOCK]:
                        s += transaction.string_form()
                    if len(organizations[org_id].blockchain.blocks) == 0:
                        s += encodeSHA256('0')
                    else:
                        s += organizations[org_id].blockchain.blocks[-1].get_hash()
                    s += nonce
                    if encodeSHA256(s).startswith('0' * ZERO_COUNT): # Mined
                        if len(organizations[org_id].blockchain.blocks) == 0:
                            organizations[org_id].blockchain.blocks.append(
                                Block(encodeSHA256('0'), organizations[org_id].transaction_pool[:TRANSACTIONS_IN_BLOCK], nonce))
                        else:
                            prev_hash = organizations[org_id].blockchain.blocks[-1].get_hash()
                            organizations[org_id].blockchain.blocks.append(
                                Block(prev_hash, organizations[org_id].transaction_pool[:TRANSACTIONS_IN_BLOCK], nonce))
                        organizations[org_id].transaction_pool = organizations[org_id].transaction_pool[TRANSACTIONS_IN_BLOCK:]
                        print('Mined new block')
                        # for neigh in organizations[org_id].neighbours:
                        for neigh in organizations[org_id].neighbours + [get_ip()]:
                            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            s.connect((neigh, SEND_NEIGHBOUR_PORT))
                            query = ['Suggest blockchain', org_id, organizations[org_id].blockchain, organizations[org_id].transaction_pool]
                            s.send(pickle.dumps(query))
                            s.close()

    def terminate(self):
        self.terminated = True

    def stop(self):
        self.stopped = True

    def resume(self):
        self.stopped = False


def query_coeff(org_id, ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((SERVER_IP, SEND_SERVER_PORT))
    query = ['coeff', org_id, ip]
    s.send(pickle.dumps(query))
    res = pickle.loads(s.recv(1024))
    s.close()
    return res


def print_menu():
    print("help\nenter organization\ncreate organization\ncreate proposal\nvote\ncontribute\nobserve blockchain\nnotifications\nexit")


miner = Miner()


def main():
    listen_n = ListenNeighbours()
    listen_s = ListenServer()
    proposal_accountant = ProposalAccountant()
    listen_n.start()
    listen_s.start()
    proposal_accountant.start()
    miner.start()

    print_menu()
    cmd = input()
    while cmd != 'exit':
        if cmd == "help":
            print_menu()
        elif cmd == "enter organization":
            print("enter its id")
            try:
                org_id = int(input())
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((SERVER_IP, SEND_SERVER_PORT))
                query = ["enter", org_id]
                s.send(pickle.dumps(query))
                ans_encoded = s.recv(1024)
                ans = pickle.loads(ans_encoded)
                if ans == 'No organization':
                    print(ans)
                elif ans == 'Already in the organization':
                    print(ans)
                else:  # neighbours
                    print('Success')
                    organizations[org_id] = OrgInfo()
                    organizations[org_id].set_neighbours(ans)
                    for ip in ans:
                        print('New neighbour ' + ip)
                    for i in organizations[org_id].neighbours:
                        s_neigh = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s_neigh.connect((i, SEND_NEIGHBOUR_PORT))
                        query_neigh = ["Add neighbour", org_id]
                        s_neigh.send(pickle.dumps(query_neigh))
                        s_neigh.close()
            except Exception:
                print('Invalid input')
        elif cmd == "create organization":
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((SERVER_IP, SEND_SERVER_PORT))
            print("enter its id")
            try:
                org_id = int(input())
                query = ["create organization", org_id]
                s.send(pickle.dumps(query))
                ans_encoded = s.recv(1024)
                ans = pickle.loads(ans_encoded)
                print(ans)
                if ans == 'Success':
                    organizations[org_id] = OrgInfo()
                s.close()
            except Exception:
                print('Invalid input')
        elif cmd == "create proposal":
            print("Specify the id of the organization")
            try:
                org_id = int(input())
                if org_id not in organizations.keys():
                    print('Try again, no such organization')
                else:
                    print("Specify the proposal")
                    content = input()
                    print("Specify the end time of the proposal(in format yyyy.mm.dd.hh.mm)")
                    start = datetime.datetime.now()
                    end_s = input()
                    end = datetime.datetime(int(end_s[0:4]), int(end_s[5:7]), int(end_s[8:10]),
                                            int(end_s[11:13]), int(end_s[14:16]))
                    if end < start:
                        print(start)
                        print(end)
                        print('Try again, incorrect date')
                    else:
                        print('Success')
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect((SERVER_IP, SEND_SERVER_PORT))
                        query = ['create proposal', org_id, content, start, end]
                        s.send(pickle.dumps(query))
                        s.close()
            except Exception:
                print('Invalid input')
        elif cmd == "vote":
            try:
                print("Specify the id of the organization")
                org_id = int(input())
                print("Specify the proposal. The relevant ones are:")
                for proposal in organizations[org_id].proposals:
                    print(proposal.info())
                proposal = input()
                print("What is your vote(Y or N)")
                vote = input()
                if vote not in ['Y', 'N']:
                    print('Try again, input should be Y or N')
                else:
                    print('Success')
                    transaction = Transaction(org_id, proposal, SELF_IP, vote, sign(PRIVATE_KEY, encode_vote_info(org_id, proposal, SELF_IP, vote)))
                    query = ['Vote', transaction, serialize_key(PUBLIC_KEY)]
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((SELF_IP, SEND_NEIGHBOUR_PORT))
                    s.send(pickle.dumps(query))
                    s.close()
            except Exception:
                print('Invalid input')
        elif cmd == "notifications":
            if len(notifications) == 0:
                print("You have no notifications")
            for notification in notifications:
                print(notification)
            notifications.clear()
        elif cmd == "contribute":
            try:
                print("Specify the id of the organization")
                org_id = int(input())
                if org_id not in organizations.keys():
                    print("Try again, you have not entered the organization")
                else:
                    print("Specify the sum of the contribution")
                    sum = int(input())
                    print("Success")
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((SERVER_IP, SEND_SERVER_PORT))
                    query = ['contribute', org_id, sum]
                    s.send(pickle.dumps(query))
                    s.close()
            except Exception:
                print('Invalid input')
        elif cmd == 'observe blockchain':
            try:
                print("Specify the id of the organization")
                org_id = int(input())
                print("The information is in blockchain" + str(org_id) + '.txt')
                organizations[org_id].blockchain.print(org_id)
            except Exception:
                print('Invalid input')
        else:
            print("Try again, incorrect command")
        cmd = input()
    sock_ex = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_ex.connect((SELF_IP, LISTEN_NEIGHBOURS_PORT))
    query = ["exit"]
    sock_ex.send(pickle.dumps(query))
    sock_ex.close()
    sock_ex2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_ex2.connect((SELF_IP, LISTEN_SERVER_PORT))
    query = ["exit"]
    sock_ex2.send(pickle.dumps(query))
    sock_ex2.close()
    proposal_accountant.terminate()
    miner.terminate()


if __name__ == "__main__":
    main()
