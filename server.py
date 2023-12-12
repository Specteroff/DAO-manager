import socket, pickle, random
from utils import *

LISTEN_NODE_PORT = 12346
SEND_NODE_PORT = 12347


class OrgInfo:
    def __init__(self, first_el):
        self.ips = [first_el]
        self.graph = {first_el: []}
        self.proposals = []
        self.contribution = {first_el: 0}
        self.total_contribution = 0

    def dfs_for_connectivity_check(self, v, visited):
        visited.add(v)
        for u in self.graph[v]:
            if u not in visited:
                self.dfs_for_connectivity_check(u, visited)

    def is_connected(self):
        if len(self.ips) == 0:
            return True
        visited = set()
        self.dfs_for_connectivity_check(self.ips[0], visited)
        return len(visited) == len(self.ips)

    def tell_active_proposals(self, ip):
        to_del = []
        for proposal in self.proposals:
            if proposal.expired():
                to_del.append(proposal)
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((ip, SEND_NODE_PORT))
                msg = ['New proposal', proposal.org_id, proposal.content, proposal.start, proposal.end]
                s.send(pickle.dumps(msg))
                s.close()
        for proposal in to_del:
            self.proposals.remove(proposal)

    # returns neighbours or True if already there
    def insert(self, ip):
        if ip in self.ips:
            return 'Already in the organization'
        self.ips.append(ip)
        self.graph[ip] = []
        self.contribution[ip] = 0
        neigh = set()
        while True:
            cnt = random.randint(1, len(self.ips) - 1)
            while len(neigh) != cnt:
                neigh.add(self.ips[random.randint(0, len(self.ips) - 2)])
            for i in neigh:
                self.graph[ip].append(i)
                self.graph[i].append(ip)
            if self.is_connected():
                return neigh
            for i in neigh:
                self.graph[ip].remove(i)
                self.graph[i].remove(ip)
            neigh.clear()

    def create_proposal(self, proposal):
        self.proposals.append(proposal)
        for ip in self.ips:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ip, SEND_NODE_PORT))
            msg = ['New proposal', proposal.org_id, proposal.content, proposal.start, proposal.end]
            s.send(pickle.dumps(msg))
            s.close()


organizations = {}


def is_such_org(org_id):
    return True if org_id in organizations.keys() else False


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((get_ip(), LISTEN_NODE_PORT))
    s.listen(10)
    while True:
        c_s, c_addr = s.accept()
        query_encoded = c_s.recv(1024)
        query = pickle.loads(query_encoded)
        cmd = query[0]
        if cmd == "organizations":
            pass
        elif cmd == "enter":
            resp = ''
            org_id = query[1]
            ip = c_addr[0]
            if not is_such_org(org_id):
                resp = 'No organization'
            else:
                resp = organizations[org_id].insert(ip)
            c_s.send(pickle.dumps(resp))
            organizations[org_id].tell_active_proposals(ip)
        elif cmd == "create organization":
            resp = ''
            org_id = query[1]
            ip = c_addr[0]
            if is_such_org(org_id):
                resp = 'Already created'
            else:
                organizations[org_id] = OrgInfo(ip)
                resp = 'Success'
            c_s.send(pickle.dumps(resp))
        elif cmd == 'create proposal':
            org_id = query[1]
            content = query[2]
            start = query[3]
            end = query[4]
            organizations[org_id].create_proposal(Proposal(org_id, content, start, end))
        elif cmd == 'contribute':
            org_id = query[1]
            sum = query[2]
            ip = c_addr[0]
            organizations[org_id].contribution[ip] += sum
            organizations[org_id].total_contribution += sum
        elif cmd == 'coeff':
            org_id = query[1]
            ip = query[2]
            resp = 0
            if organizations[org_id].total_contribution > 0:
                resp = organizations[org_id].contribution[ip] / organizations[org_id].total_contribution
            c_s.send(pickle.dumps(resp))
        c_s.close()


if __name__ == "__main__":
    main()
