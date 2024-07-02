#!/usr/bin/env python3

import stl
import sys
import numpy as np
import textwrap
import argparse

parser = argparse.ArgumentParser(description="Calculates how to string tubes together to make objects")
parser.add_argument("file", help="STL file to analyze")
parser.add_argument("-s", "--scale", type=float, help="scale factor for the tube lengths", default=1)
args = parser.parse_args()

mesh = stl.mesh.Mesh.from_file(args.file)

# 1. Convert list of triangle coordinates to vertex coordinates + triangle indices
#    (obj-style representation)

n_triangles = len(mesh.vectors)
points = mesh.vectors.reshape(3 * n_triangles, 3)
(vertices, triangles) = np.unique(points, return_inverse=True, axis=0)
triangles = triangles.reshape(n_triangles, 3)

# 2. Ensure the mesh is closed by testing that every edge has two triangles
#    wound in opposite directions

edges = np.hstack((triangles[:, 0:2],
                   triangles[:, 1:3],
                   triangles[:, 2:3], triangles[:,0:1])).reshape(n_triangles * 3, 2)

edges_reversed = edges[:,::-1]
(_, counts) = np.unique(np.vstack((edges, edges_reversed)), return_counts=True, axis=0)
if not np.all(counts == 2):
    print("WARNING: Mesh is not closed. Output may be incorrect. Please repair mesh with netfabb.", file=sys.stderr)

# 3. Create a linked list representation of a string threading
#    that naively runs around each face.

winding_next = (3 * np.arange(n_triangles)).repeat(3) + np.tile(np.array([1, 2, 0]), n_triangles)

# 4. Create a graph of face connectivity

edges_sorted = edges.copy()
edges_sorted.sort(axis=1)
(unique_edges, edge_indices) = np.unique(edges_sorted, return_inverse=True, axis=0)
edge_indices = edge_indices.reshape(n_triangles, 3)
#print(edge_indices)

face_connections = {i: set() for i in range(n_triangles)}
for i in range(n_triangles):
    for j in range(i + 1, n_triangles):
        for e1 in range(3):
            if edge_indices[i][e1] in edge_indices[j]:
                e2 = list(edge_indices[j]).index(edge_indices[i][e1])
                face_connections[i].add((j, e1, e2)) 
                face_connections[j].add((i, e2, e1))

# 5. Find a spanning tree of this graph using DFS

#print(face_connections)

unvisited = set(face_connections)
result = []
while unvisited:
    to_visit = [(None, None, next(iter(unvisited)), None)]
    while to_visit:
        (f1, e1, f2, e2) = to_visit.pop()
        if f2 in unvisited:
            if f1 is not None:
                result.append((f1, e1, f2, e2))
            unvisited.remove(f2)
            for (nf, e1, e2) in face_connections[f2]:
                #to_visit.append((f2, e1, nf, e2))  # DFS
                to_visit.insert(0, (f2, e1, nf, e2))  # BFS

# 6. Introduce a twist on every edge crossed in the spanning tree

for (f1, e1, f2, e2) in result:
    i1 = f1 * 3 + e1
    i2 = f2 * 3 + e2
    assert np.all(edges_sorted[i1] == edges_sorted[i2]), "Tried to twist a non-shared edge"

    if not np.all(edges[i1] == edges[i2]):
        # We need to reverse the linked list of i2
        loop = []
        start = i2
        cur = start
        while True:
            loop.append(cur)
            cur = winding_next[cur]
            if cur == start:
                break
        edges[loop] = edges[loop,::-1]
        nexts = np.hstack((loop[-1:], loop[0:-1]))
        winding_next[loop] = nexts

    # Twist the linked list
    next1 = winding_next[i1]
    next2 = winding_next[i2]
    winding_next[i1] = next2
    winding_next[i2] = next1

# 7. Walk the linked list
unvisited = set(np.arange(len(edges)))
strings = []
while unvisited:
    string = []
    edge = unvisited.pop()
    string.append(edge)
    while True:
        edge = winding_next[edge]
        if edge == string[0]:
            strings.append(string)
            break
        assert edge in unvisited, "Tried to branch the string"
        string.append(edge)
        unvisited.remove(edge)

# 8. Print the output
n_letters = int(np.ceil(np.log(len(unique_edges)) / np.log(26)))
numbers_seen = {}
next_number = 0
def number_to_letters(n):
    global next_number
    if n not in numbers_seen:
        numbers_seen[n] = next_number
        n = next_number
        next_number += 1
    else:
        n = numbers_seen[n]
    result = ""
    for i in range(n_letters):
        result = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[n % 26] + result
        n //= 26
    return result

numbers_reversed = {}
def to_letters(e):
    (i, rev) = e
    if i not in numbers_reversed:
        numbers_reversed[i] = rev
        rev = False
    else:
        rev ^= numbers_reversed[i]
    return number_to_letters(i) + ("'" if rev else "")

unique_edge_list = unique_edges.tolist()
def get_unique_edge_index(e):
    e_fwd = list(edges[e])
    try:
        return (unique_edge_list.index(e_fwd), False)
    except ValueError:
        pass
    try:
        e_rev = list(reversed(e_fwd))
        return (unique_edge_list.index(e_rev), True)
    except ValueError as e:
        raise AssertionError("Could not find edge in unique edgelist") from e

# Calculate the stringing first, so that letters are sorted correctly

stringing_text = [" - ".join(to_letters(get_unique_edge_index(e)) for e in string) for string in strings]

def edge_length(edge):
    pt1 = vertices[edge[0]]
    pt2 = vertices[edge[1]]
    length = np.linalg.norm(pt2 - pt1)
    return length

tubes = [(number_to_letters(i), edge_length(edge) * args.scale) for (i, edge) in enumerate(unique_edges)]
tubes.sort(key=lambda x: x[0])

print("Tubes:", len(unique_edges))
for (n, l) in tubes:
    print(n, l)
print()

print("Threading order:")
for t in stringing_text:
    print(textwrap.fill(t, 34))
    print()
