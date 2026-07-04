# Coding Standards

## Rust Conventions

- Follow rustfmt defaults
- Use `thiserror` for error types, `anyhow` for application errors
- File naming: snake_case for modules, PascalCase for types
- Prefer `&str` over `String` in function parameters
- Use `impl Trait` in return positions sparingly
- Testing: `#[cfg(test)]` modules co-located with source
- Documentation: doc comments on all public items
