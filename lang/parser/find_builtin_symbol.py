
def find_builtin_symbol(source: str):
    from . import builtin_symbols

    for symbol in builtin_symbols.builtin_symbols():
        if symbol.source == source:
            return symbol
    return None


def find_generic_builtin_symbol_builder(source: str):
    from . import builtin_symbols

    for builder in builtin_symbols.generic_builtin_symbols_builders():
        if builder.source == source:
            return builder
    return None
