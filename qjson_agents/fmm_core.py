from __future__ import annotations

class FractalMemory:
    def __init__(self):
        self.memory_tree = {}

    def insert(self, topic_path, data):
        node = self.memory_tree
        for part in topic_path:
            if part not in node:
                node[part] = {}
            node = node[part]
        if '__data__' not in node:
            node['__data__'] = []
        node['__data__'].append(data)

    def query(self, topic_path):
        node = self.memory_tree
        for part in topic_path:
            if part not in node:
                return []
            node = node[part]
        return node.get('__data__', [])

    def visualize(self, node=None, prefix=''):
        if node is None:
            node = self.memory_tree
        for k, v in node.items():
            if k == '__data__':
                continue
            print(prefix + k + '/')
            self.visualize(v, prefix + '  ')

