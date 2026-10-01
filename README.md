# tornado-demix has moved

This repository is archived. The project continues as
**[TornadoCash-demixer](https://github.com/prettydeath/TornadoCash-demixer)**.

The new version covers 8 EVM chains (55 pools, native and ERC-20), reports every
exit candidate with an evidence band and the evidence behind it, and measures on
real depositors with a placebo (target-decoy) test which signals stand above chance.
It also groups exits paid out together, links wallets of one operator and traces
withdrawn funds forward.

```bash
python -m pip install tornado-demix
```

- Code and documentation: https://github.com/prettydeath/TornadoCash-demixer
- Docs site: https://prettydeath.github.io/TornadoCash-demixer/
- PyPI: https://pypi.org/project/tornado-demix/

The original amount + timing toolkit (Ethereum ETH pools only) remains in this
repository's git history. Its main heuristic, a count match in a time window, turned
out to fire as often in decoy windows as in real ones, so it should not be used as
evidence on its own.
