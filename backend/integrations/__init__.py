"""Butler Hermes Integration Layer

This package provides the dedicated import/adapter layer for Hermes-derived code
into the Butler backend. All Hermes imports must live behind this layer so Butler
can expose a stable product architecture while moving fast through aggressive reuse.

## Non-Negotiables

- Hermes-derived code stays under `backend/integrations/hermes/`
- Butler APIs and domain logic must NOT depend on raw Hermes entrypoints directly
- No CLI/TUI surface is exposed as Butler product behavior
- Butler docs override Hermes when behavior conflicts
"""