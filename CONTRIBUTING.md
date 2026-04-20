# Contributing to Mnemosyne

Thanks for your interest. Mnemosyne is a small, focused project. We welcome contributions that align with its core principles: **local-first, zero-cloud, minimal dependencies**.

## Getting Started

```bash
git clone https://github.com/AxDSan/mnemosyne.git
cd mnemosyne
pip install -e ".[dev]"
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## What We're Looking For

- Bug fixes
- Performance improvements
- Better error messages and logging
- Documentation improvements

## What We're Not Looking For

- Cloud backends or hosted services
- Heavy dependencies (prefer stdlib or small, stable packages)
- Features that compromise the zero-config, local-first design

## Pull Request Process

1. Open an issue first to discuss non-trivial changes
2. Keep commits focused and atomic
3. Include tests for new behavior
4. Update README.md if user-facing behavior changes

## Questions?

Open a [GitHub issue](https://github.com/AxDSan/mnemosyne/issues) or start a discussion.
