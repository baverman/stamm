from __future__ import annotations

from dataclasses import dataclass, field

from .index import IndexedMessage


@dataclass
class Node:
    identifier: str
    message: IndexedMessage | None = None
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)


@dataclass(frozen=True)
class ThreadRow:
    message: IndexedMessage
    depth: int


def build_threads(messages: list[IndexedMessage]) -> list[ThreadRow]:
    nodes: dict[str, Node] = {}
    anonymous: list[Node] = []
    current_nodes: list[Node] = []

    def node(identifier: str) -> Node:
        return nodes.setdefault(identifier, Node(identifier))

    for index, message in enumerate(messages):
        if message.message_id:
            shared = node(message.message_id)
            if shared.message is None:
                current = shared
                current.message = message
            else:
                # A duplicate Message-ID must not hide a visible message.
                current = Node(f'duplicate:{index}', message)
                anonymous.append(current)
        else:
            current = Node(f'anonymous:{index}', message)
            anonymous.append(current)
        current_nodes.append(current)

    def link(parent: Node, child: Node) -> None:
        if parent is child or child.parent is not None:
            return
        ancestor: Node | None = parent
        while ancestor:
            if ancestor is child:
                return
            ancestor = ancestor.parent
        child.parent = parent
        parent.children.append(child)

    for index, message in enumerate(messages):
        current = current_nodes[index]
        chain = [node(identifier) for identifier in message.references]
        for parent, child in zip(chain, chain[1:]):
            link(parent, child)
        if chain:
            link(chain[-1], current)
        elif message.in_reply_to:
            link(node(message.in_reply_to), current)

    all_nodes = list(nodes.values()) + anonymous
    roots = [item for item in all_nodes if item.parent is None]

    def freshness(item: Node) -> float:
        own = item.message.timestamp if item.message else float('-inf')
        return max([own, *(freshness(child) for child in item.children)])

    roots.sort(key=freshness)
    rows: list[ThreadRow] = []

    def visit(item: Node, visible_depth: int) -> None:
        next_depth = visible_depth
        if item.message:
            rows.append(ThreadRow(item.message, visible_depth))
            next_depth += 1
        item.children.sort(key=lambda child: child.message.timestamp if child.message else freshness(child))
        for child in item.children:
            visit(child, next_depth)

    for root in roots:
        visit(root, 0)
    return rows
