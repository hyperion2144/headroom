# Design: c3-cli-stubs

## Context & Goals

Register `wrap omp` and `unwrap omp` CLI commands as stubs in headroom/cli/wrap.py.
Already implemented and tested.

## Technical Approach
Follows the Click command pattern from wrap opencode. Stubs raise NotImplementedError.

## File Manifest
| File | Action |
|------|--------|
| headroom/cli/wrap.py | Modify (done) |
