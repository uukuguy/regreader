# Changelog

All notable changes to RegReader will be documented in this file.

## [0.1.0] - 2026-01-14

### Changed - Project Rename
- **BREAKING**: Renamed project from GridCode to RegReader
- **BREAKING**: Package name changed from `grid-code` to `regreader`
- **BREAKING**: CLI command changed from `gridcode` to `regreader`
- **BREAKING**: Python package changed from `grid_code` to `regreader`
- **BREAKING**: Environment variables changed from `GRIDCODE_*` to `REGREADER_*`
- **BREAKING**: Core classes renamed:
  - `GridCodeSettings` → `RegReaderSettings`
  - `GridCodeError` → `RegReaderError`
  - `GridCodeMCPClient` → `RegReaderMCPClient`
  - `GridCodeTools` → `RegReaderTools`
  - `GridCodeToolsProtocol` → `RegReaderToolsProtocol`
  - `GridCodeMCPToolsAdapter` → `RegReaderMCPToolsAdapter`

### Added
- CHANGELOG.md to track project changes
- Documentation archive structure for historical reference

### Removed
- Obsolete documentation files (8 files)
- Outdated main branch documentation

### Migration Guide
For existing users migrating from GridCode:

1. **Uninstall old package**:
   ```bash
   pip uninstall grid-code
   ```

2. **Install new package**:
   ```bash
   pip install regreader
   ```

3. **Update environment variables** in your `.env` file:
   - Rename all `GRIDCODE_*` variables to `REGREADER_*`

4. **Update CLI commands**:
   - Replace `gridcode` with `regreader` in all scripts

5. **Update Python imports** (if using as library):
   ```python
   # Old
   from grid_code.config import GridCodeSettings

   # New
   from regreader.config import RegReaderSettings
   ```

## Project Focus
RegReader focuses on professional understanding of power grid regulations (电网规程专业理解).
