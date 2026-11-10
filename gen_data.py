"""
Seed database with realistic exam answers and planted anomalies.

Planted for demo:
  S047 – Data Structures (exam 5, hard): score spike, near-copy of S052 answers, high on hard paper
  S019 – DBMS (exam 3): large internal–external gap + score spike

Answers are real subject-related text (not random tokens), so TF-IDF similarity
reflects actual shared wording when a student copies.
"""
import random
import numpy as np
from db import init, conn

random.seed(7)
np.random.seed(7)
init()
c = conn()

N = 60
SUBJECTS = [
    ("Maths", "medium"),
    ("Physics", "easy"),
    ("DBMS", "medium"),
    ("OS", "easy"),
    ("Data Structures", "hard"),
]

for i in range(1, N + 1):
    c.execute(
        "INSERT INTO students VALUES (?,?,?,?)",
        (f"S{i:03d}", f"Student {i}", "AI&DS", 2),
    )
for e, (sub, diff) in enumerate(SUBJECTS, 1):
    c.execute(
        "INSERT INTO exams VALUES (?,?,?,?,?)",
        (e, sub, "external", f"2026-0{e}-15", diff),
    )

# Base ability; S047 and S019 set average so spikes stand out
base = {f"S{i:03d}": random.randint(45, 80) for i in range(1, N + 1)}
base["S047"] = 55
base["S019"] = 55
pen = {"easy": 5, "medium": 0, "hard": -15}

for e, (sub, diff) in enumerate(SUBJECTS, 1):
    for s in base:
        ext = int(np.clip(base[s] + pen[diff] + np.random.normal(0, 5), 0, 100))
        internal = int(np.clip(base[s] + np.random.normal(0, 4), 0, 100))
        if (s, e) == ("S047", 5):
            ext = min(100, base[s] + 38)  # spike on hard paper
        if (s, e) == ("S019", 3):
            ext = min(100, base[s] + 35)
            internal = base[s] - 12  # large gap
        c.execute(
            "INSERT INTO marks(student_id,exam_id,marks,internal_marks) VALUES (?,?,?,?)",
            (s, e, ext, internal),
        )

# --- Realistic Data Structures answers (exam 5), 5 questions ---
# Bank of distinct model answers so random students are NOT similar.
BANK = {
    1: [
        "A stack is a LIFO structure. Push adds on top and pop removes from top. Used in expression evaluation recursion and undo features in editors.",
        "Queue follows FIFO order. Enqueue inserts at rear dequeue removes from front. Applied in scheduling breadth first search and printer jobs.",
        "Array stores elements in contiguous memory with constant time index access. Insertion and deletion in the middle cost linear time due to shifting.",
        "Linked list nodes hold data and a next pointer. Insert and delete need only pointer updates. Random access is slow because traversal is sequential.",
        "Hash table maps keys to buckets with a hash function. Average lookup is constant time. Collisions are handled by chaining or open addressing.",
    ],
    2: [
        "Binary tree each node has at most two children left and right. Traversals include inorder preorder and postorder for different processing orders.",
        "BST keeps left subtree keys smaller and right larger. Search insert delete average logarithmic height when the tree stays balanced.",
        "AVL tree is a balanced BST. Rotations after insert or delete restore height balance so operations stay logarithmic in the worst case.",
        "Heap is a complete binary tree used for priority queues. Parent is ordered above children. Insert and extract-min are logarithmic.",
        "Graph is vertices and edges. Adjacency list saves space for sparse graphs. Adjacency matrix gives constant edge checks but uses more memory.",
    ],
    3: [
        "BFS explores level by level using a queue. Finds shortest path in unweighted graphs. Visited set prevents revisiting nodes.",
        "DFS goes deep along one path using a stack or recursion. Useful for cycle detection topological sort and connected components.",
        "Dijkstra finds shortest paths from a source with non-negative weights. Uses a priority queue and relaxes edges until distances settle.",
        "Dynamic programming solves overlapping subproblems with memoization or tabulation. Examples include knapsack LCS and matrix chain order.",
        "Greedy picks the locally best choice at each step. Works for activity selection Huffman coding and fractional knapsack when the property holds.",
    ],
    4: [
        "Time complexity describes how runtime grows with input size. Big O gives an upper bound. Binary search is logarithmic linear search is linear.",
        "Space complexity measures extra memory. In-place algorithms use constant extra space. Merge sort needs linear auxiliary arrays.",
        "Stable sort keeps equal keys in original order. Merge sort is stable. Quick sort is not stable unless extra care is taken.",
        "Divide and conquer splits a problem into subproblems solves them and combines results. Merge sort and quick sort follow this pattern.",
        "Amortized analysis averages cost over a sequence of operations. Dynamic array append is amortized constant despite occasional resizing.",
    ],
    5: [
        "Primary index is sorted on the key and speeds equality and range queries. Secondary index supports alternate search attributes.",
        "B-tree keeps keys sorted in multiway nodes and stays balanced. Disk-friendly because each node can store many keys per block.",
        "Collision resolution in hashing uses chaining with lists or open addressing with linear quadratic or double hashing probes.",
        "Topological sort orders vertices in a DAG so every edge goes forward. Kahn algorithm and DFS finishing times both compute it.",
        "Minimum spanning tree connects all vertices with minimum total edge weight. Kruskal uses sorted edges and Union-Find. Prim grows a tree from a start vertex.",
    ],
}

# S052 model answers (source that S047 will nearly copy)
S052 = {
    1: "A stack is LIFO. Push places an item on top and pop removes the top item. Stacks evaluate postfix expressions support recursion call frames and implement undo in text editors.",
    2: "A binary search tree orders keys so left children are smaller and right children are larger. Average search insert and delete are logarithmic when the tree remains reasonably balanced.",
    3: "Breadth first search uses a queue to visit nodes level by level. It finds the shortest path in an unweighted graph and needs a visited set to avoid cycles.",
    4: "Big O notation bounds how an algorithm scales. Binary search on a sorted array is O(log n). Scanning every element is O(n). Nested loops over n often give O(n squared).",
    5: "Kruskal builds an MST by sorting edges and adding the next edge that does not form a cycle using Union-Find. Prim grows the tree from one vertex by always adding the cheapest edge out.",
}

# S047 near-copy of S052 (small edits only — high cosine similarity)
S047 = {
    1: "A stack is LIFO. Push places an item on top and pop removes the top item. Stacks evaluate postfix expressions support recursion call frames and implement undo in text editors.",
    2: "A binary search tree orders keys so left children are smaller and right children are larger. Average search insert and delete are logarithmic when the tree remains reasonably balanced.",
    3: "Breadth first search uses a queue to visit nodes level by level. It finds the shortest path in an unweighted graph and needs a visited set to avoid cycles.",
    4: "Big O notation bounds how an algorithm scales. Binary search on a sorted array is O(log n). Scanning every element is O(n). Nested loops over n often give O(n squared).",
    5: "Kruskal builds an MST by sorting edges and adding the next edge that does not form a cycle using Union-Find. Prim grows the tree from one vertex by always adding the cheapest edge out.",
}
# Tiny paraphrases so not 100% identical character-for-character
S047[1] = S047[1].replace("places an item", "puts an item").replace("text editors", "editors")
S047[3] = S047[3].replace("needs a visited set", "uses a visited set")

for s in base:
    for q in range(1, 6):
        if s == "S047":
            text = S047[q]
        elif s == "S052":
            text = S052[q]
        else:
            text = random.choice(BANK[q])
        c.execute(
            "INSERT INTO answers(student_id,exam_id,question_no,response) VALUES (?,?,?,?)",
            (s, 5, q, text),
        )

c.commit()
c.close()
print("Done. Realistic DS answers loaded.")
print("Planted: S047 (spike + copy of S052 + hard paper), S019 (gap + spike)")
