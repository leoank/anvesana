"""Console output shared by all benchmarks and commands."""

from __future__ import annotations

RULE = "=" * 64


def banner(title: str, *lines: str):
    print(RULE)
    print(f" {title}")
    for line in lines:
        print(f" {line}")
    print(RULE, flush=True)


def step(msg: str):
    print(f"\n{msg}", flush=True)


def report(label: str, value: float, unit: str, extra: str = ""):
    print(f"  -> {label:<32}: {value:>10,.2f} {unit}{'  ' + extra if extra else ''}", flush=True)


def summary(title: str, metrics):
    print(f"\n{'=' * 16} {title} {'=' * max(4, 46 - len(title))}")
    for m in metrics:
        print(f" {m.name:<44} {m.value:>12,.2f} {m.unit}")
    print(RULE, flush=True)


class Table:
    """Plain-text or Markdown table; first column left-aligned, the rest right-aligned."""

    def __init__(self, title: str, headers: list[str]):
        self.title, self.headers, self.rows = title, headers, []

    def add(self, *cells):
        self.rows.append([str(c) for c in cells])

    def text(self) -> str:
        widths = [max([len(h)] + [len(r[i]) for r in self.rows]) for i, h in enumerate(self.headers)]

        def line(cells):
            return "  ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(cells, widths)))

        out = [f"\n{self.title}", "-" * (sum(widths) + 2 * (len(widths) - 1)), line(self.headers)]
        return "\n".join(out + [line(r) for r in self.rows])

    def markdown(self) -> str:
        out = [f"\n### {self.title}\n", "| " + " | ".join(self.headers) + " |",
               "|" + "|".join("---" if i == 0 else "---:" for i in range(len(self.headers))) + "|"]
        return "\n".join(out + ["| " + " | ".join(r) + " |" for r in self.rows])


def num(v, digits: int = 2) -> str:
    return "-" if v is None else f"{v:,.{digits}f}"
