"""Header-based thread graph construction."""

from __future__ import annotations

from dataclasses import dataclass, field

from .index import IndexedMessage


@dataclass
class _Node:
    identifier: str
    message: IndexedMessage | None = None
    parent: _Node | None = None
    children: list[_Node] = field(default_factory=list)


@dataclass(frozen=True)
class ThreadRow:
    message: IndexedMessage
    depth: int


def build_threads(messages: list[IndexedMessage]) -> list[ThreadRow]:
    """Return all visible messages in root-freshness and tree order."""
    nodes: dict[str, _Node] = {}
    anonymous: list[_Node] = []
    current_nodes: list[_Node] = []

    def node(identifier: str) -> _Node:
        return nodes.setdefault(identifier, _Node(identifier))

    for index, message in enumerate(messages):
        if message.message_id:
            shared = node(message.message_id)
            if shared.message is None:
                current = shared
                current.message = message
            else:
                # A duplicate Message-ID must not hide a visible message.
                current = _Node(f'duplicate:{index}', message)
                anonymous.append(current)
        else:
            current = _Node(f'anonymous:{index}', message)
            anonymous.append(current)
        current_nodes.append(current)

    def link(parent: _Node, child: _Node) -> None:
        if parent is child or child.parent is not None:
            return
        ancestor: _Node | None = parent
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

    def freshness(item: _Node) -> float:
        own = item.message.timestamp if item.message else float('-inf')
        return max([own, *(freshness(child) for child in item.children)])

    roots.sort(key=freshness)
    rows: list[ThreadRow] = []

    def visit(item: _Node, visible_depth: int) -> None:
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
