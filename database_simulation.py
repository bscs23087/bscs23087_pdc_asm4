class LamportNode:
    def __init__(self, node_id):
        self.node_id = node_id
        self.balance = 100
        self.lc = 0
        self.update_log = []

    def local_update(self, new_balance):
        self.lc += 1
        self.balance = new_balance
        self.update_log.append((self.lc, self.node_id, self.balance))
        print(f"[Lamport] Node {self.node_id} local update: Balance=${self.balance}, LC={self.lc}")
        return self.lc, self.balance

    def receive_message(self, sender_id, msg_lc, msg_balance):
        self.lc = max(self.lc, msg_lc) + 1
        print(f"[Lamport] Node {self.node_id} received UPDATE from {sender_id}: Balance=${msg_balance}, LC={msg_lc}. New LC={self.lc}")
        self.update_log.append((msg_lc, sender_id, msg_balance))
        # Re-apply all updates in strictly Lamport timestamp order
        self.update_log.sort(key=lambda x: (x[0], x[1]))
        # Apply in order
        for lc, nid, bal in self.update_log:
            self.balance = bal
        print(f"[Lamport] Node {self.node_id} applied updates. Current Balance=${self.balance}")


class VectorNode:
    def __init__(self, node_id, index):
        self.node_id = node_id
        self.index = index
        self.balance = 100
        self.vc = [0, 0, 0] # A=0, B=1, C=2

    def local_update(self, new_balance):
        self.vc[self.index] += 1
        self.balance = new_balance
        print(f"[Vector] Node {self.node_id} local update: Balance=${self.balance}, VC={self.vc}")
        return list(self.vc), self.balance

    def check_causality(self, v_local, v_incoming):
        # A strictly happened-before B if for all i, A[i] <= B[i] and there is at least one i where A[i] < B[i].
        # We need to check if v_incoming strictly happened-after v_local.
        # This means v_local strictly happened-before v_incoming.
        # Wait, strictly happened-after means v_incoming dominates v_local.
        
        incoming_is_greater_or_equal = all(v_incoming[i] >= v_local[i] for i in range(3))
        incoming_is_strictly_greater = incoming_is_greater_or_equal and any(v_incoming[i] > v_local[i] for i in range(3))
        
        local_is_greater_or_equal = all(v_local[i] >= v_incoming[i] for i in range(3))
        
        if incoming_is_strictly_greater:
            return "HAPPENED_AFTER"
        elif local_is_greater_or_equal:
            return "HAPPENED_BEFORE"
        else:
            return "CONCURRENT"

    def receive_message(self, sender_id, msg_vc, msg_balance):
        causality = self.check_causality(self.vc, msg_vc)
        print(f"[Vector] Node {self.node_id} received UPDATE from {sender_id}: Balance=${msg_balance}, VC={msg_vc}")
        print(f"[Vector] Node {self.node_id} evaluated causality: {causality}")
        
        if causality == "HAPPENED_AFTER":
            self.balance = msg_balance
            # Update VC: max pairwise, no increment for receive according to some models, or increment local?
            # Usually, when a node receives a message, it merges the vector clocks and increments its own.
            # But the vector clock reflects the state. If we just apply it, we merge.
            self.vc = [max(self.vc[i], msg_vc[i]) for i in range(3)]
            self.vc[self.index] += 1
            print(f"[Vector] Node {self.node_id} applied update. New Balance=${self.balance}, VC={self.vc}")
        elif causality == "CONCURRENT":
            print(f"[Vector] WARNING: Replication Conflict detected at Node {self.node_id}!")
            print(f"         Cannot apply UPDATE(Balance=${msg_balance}) safely. Halting overwrite.")
            # We can choose to merge VCs or leave it. We'll just merge VCs to reflect knowledge, but not update balance.
            self.vc = [max(self.vc[i], msg_vc[i]) for i in range(3)]
            self.vc[self.index] += 1
        else:
            print(f"[Vector] Node {self.node_id} ignored outdated UPDATE.")


def run_simulation():
    print("=== INITIALIZATION ===")
    lamport_nodes = {'A': LamportNode('A'), 'B': LamportNode('B'), 'C': LamportNode('C')}
    vector_nodes = {'A': VectorNode('A', 0), 'B': VectorNode('B', 1), 'C': VectorNode('C', 2)}
    
    # Message queues to simulate network and partitions
    class Message:
        def __init__(self, sender, receiver, balance, lc=None, vc=None):
            self.sender = sender
            self.receiver = receiver
            self.balance = balance
            self.lc = lc
            self.vc = vc
            
    lamport_network = []
    vector_network = []
    
    def broadcast(sender, balance, lc, vc):
        for receiver in ['A', 'B', 'C']:
            if receiver != sender:
                lamport_network.append(Message(sender, receiver, balance, lc=lc))
                vector_network.append(Message(sender, receiver, balance, vc=vc))

    print("\n=== EVENT 1: Node A receives local request to add $50 ===")
    l_lc, l_bal = lamport_nodes['A'].local_update(150)
    v_vc, v_bal = vector_nodes['A'].local_update(150)
    broadcast('A', 150, l_lc, v_vc)
    
    print("\n=== EVENT 2: Node B receives Node A's message, then adds 10% interest ===")
    # Find A's message to B
    msg_l = next(m for m in lamport_network if m.sender == 'A' and m.receiver == 'B')
    msg_v = next(m for m in vector_network if m.sender == 'A' and m.receiver == 'B')
    
    lamport_nodes['B'].receive_message(msg_l.sender, msg_l.lc, msg_l.balance)
    vector_nodes['B'].receive_message(msg_v.sender, msg_v.vc, msg_v.balance)
    
    # Node B local update
    l_lc, l_bal = lamport_nodes['B'].local_update(165)
    v_vc, v_bal = vector_nodes['B'].local_update(165)
    broadcast('B', 165, l_lc, v_vc)
    
    print("\n=== EVENT 3: Node C partitioned, receives local withdraw $20, then partition heals ===")
    # Node C local update
    l_lc, l_bal = lamport_nodes['C'].local_update(80)
    v_vc, v_bal = vector_nodes['C'].local_update(80)
    # Network heals, C broadcasts
    broadcast('C', 80, l_lc, v_vc)
    
    print("\n=== EVENT 4: Node A receives Node C's message ===")
    msg_l = next(m for m in lamport_network if m.sender == 'C' and m.receiver == 'A')
    msg_v = next(m for m in vector_network if m.sender == 'C' and m.receiver == 'A')
    
    lamport_nodes['A'].receive_message(msg_l.sender, msg_l.lc, msg_l.balance)
    vector_nodes['A'].receive_message(msg_v.sender, msg_v.vc, msg_v.balance)

    print("\n=== EVENT 5: Node A receives Node B's message ===")
    msg_l = next(m for m in lamport_network if m.sender == 'B' and m.receiver == 'A')
    msg_v = next(m for m in vector_network if m.sender == 'B' and m.receiver == 'A')
    
    lamport_nodes['A'].receive_message(msg_l.sender, msg_l.lc, msg_l.balance)
    vector_nodes['A'].receive_message(msg_v.sender, msg_v.vc, msg_v.balance)

    print("\n=== FINAL STATE OF NODE A ===")
    print(f"Lamport Clock Final Balance at Node A: ${lamport_nodes['A'].balance}")
    print(f"Vector Clock Final Balance at Node A: ${vector_nodes['A'].balance}")

if __name__ == "__main__":
    run_simulation()
