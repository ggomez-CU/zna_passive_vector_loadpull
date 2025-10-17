**Bias Controller Guide**

- Purpose: provide a single entrypoint to read bias supply voltages from one or more channels/supplies and expose them to sequences for logging and plotting.
- Class: `BiasController` in `src/loadpull/instruments/bias_controller.py:10`.

**Setup**
- Bench resource: add a `BiasCtrl` resource under `[visa]` in your bench TOML. Example: `BiasCtrl = "192.168.0.40:5025"` (socket) or a VISA string.
- Mode and wiring:
  - Dual channel: `[bias_ctrl] mode = "dual_channel"; channels = { drain = "OUT1", gate = "OUT2" }`
  - Dual supply: `[bias_ctrl] mode = "dual_supply"; secondary = "AuxSupply"; extra_supplies = ["Extra1"]`
  - Mixed: `[bias_ctrl] mode = "mixed"; channels = {...}; secondary = "AuxSupply"`
- Example bench files: `benches/bench_default.toml:19`, `benches/bench_dual_channel.toml:18`, `benches/bench_dual_supply.toml:20`.
- Test spec: include `BiasCtrl` in `requires` and call its methods via `measure` steps. Example in `testspecs/test_registry.yaml:9` and see usage examples below.

**Workflow**
- Registration: instrument name `"BiasCtrl"` maps to `BiasController` in `src/loadpull/core/registry.py:19`.
- Instantiation: CLI iterates registry and constructs each instrument with a SCPI session in `src/loadpull/cli.py:50-52`.
- Bench config application: the CLI retrieves an instrument-specific config and, if available, calls `apply_bench_config(config, session)` in `src/loadpull/cli.py:53-55`.
- Measurement in sequences: a testspec `measure` step calls a `BiasController` method and writes a JSONL record via sequencing (`src/loadpull/core/sequencing.py:87`) and writer (`src/loadpull/core/results.py:17`).

Notes:
- `BiasController.apply_bench_config(...)` expects a dict shaped like the TOML `[bias_ctrl]` table and a `Session` capable of creating additional SCPI links for secondary supplies (see "API" below for `new_scpi_for_resource`).
- In this tree, the CLI references `Session.instrument_config(name)` (see `src/loadpull/cli.py:53`) and `BiasController` references `Session.new_scpi_for_resource(...)` (`src/loadpull/instruments/bias_controller.py:39`). Ensure your `Session` implementation provides these helpers in production.

**API**
- File: `src/loadpull/instruments/bias_controller.py:10`
- Initialization parameters:
  - `scpi` (required): primary `Scpi` session for the main supply (`src/loadpull/instruments/bias_controller.py:13`).
- Bench parameters (via `apply_bench_config`):
  - `mode`: one of `"single"`, `"dual_channel"`, `"dual_supply"`, `"mixed"` (`src/loadpull/instruments/bias_controller.py:21`).
  - `channels` (dict[str,str]): logical names to channel identifiers like `"OUT1"`, `"OUT2"` used for channel-specific voltage queries (`src/loadpull/instruments/bias_controller.py:26-29`).
  - `secondary`/`secondary_resource` (str): bench instrument key for an additional supply (`src/loadpull/instruments/bias_controller.py:31-35`).
  - `extra_supplies` (list[str]): optional list of more bench instrument keys (`src/loadpull/instruments/bias_controller.py:36-39`).

**Class I/O Table**

| Member | Inputs | Outputs | Description | Called from |
| --- | --- | --- | --- | --- |
| `__init__(scpi)` | `Scpi` primary | instance | Store primary SCPI and init mode/state | `src/loadpull/cli.py:51-52` |
| `apply_bench_config(config, session)` | `dict` config, `Session` | None | Set mode, map channels, attach secondary SCPI sessions | `src/loadpull/cli.py:53-55` |
| `read_supply()` | — | `float` | Sum of all configured segment voltages | test/sequence measure steps |
| `read_segments()` | — | `List[float]` | Last per-segment voltages (lazy measure on first use) | test/sequence measure steps |
| `_measure_channel(channel)` | `str` | `float` | Query `MEAS:VOLT? (@<channel>)` on primary | internal |
| `_measure_default(scpi)` | `Scpi` | `float` | Query `MEAS:VOLT?` on given session | internal |

Two key bullets:
- What it does: normalizes single/dual channel and single/dual supply topologies into a consistent “segments” view and exposes total supply (`read_supply`) and per-segment readings (`read_segments`).
- Where used/called: created by the CLI from the instrument registry (`src/loadpull/core/registry.py:19`, `src/loadpull/cli.py:50-55`) and invoked from testspec `measure` actions (e.g., `measure: {inst: BiasCtrl, method: read_supply}`) which persist readings to JSONL.

**Usage Examples**
- Dual-channel setup (drain/gate on one supply):
  - Bench TOML: `benches/bench_dual_channel.toml:18`
  - Testspec step:
    - `- measure: {inst: BiasCtrl, method: read_supply, save_as: Vdd_total}`
    - `- measure: {inst: BiasCtrl, method: read_segments, save_as: Vdd_segments}`
- Dual-supply setup (two instruments):
  - Bench TOML: `benches/bench_dual_supply.toml:20`
  - Testspec step:
    - `- measure: {inst: BiasCtrl, method: read_supply, save_as: supply_sum}`

**SCPI Details**
- Channel read: `MEAS:VOLT? (@<channel>)` on the primary `Scpi` (`src/loadpull/instruments/bias_controller.py:66-67`).
- Default read: `MEAS:VOLT?` on each `Scpi` session (`src/loadpull/instruments/bias_controller.py:69-70`).

**JSONL Logging**
- Each `measure` step writes a JSON line with timestamp, test, step and payload (`src/loadpull/core/results.py:17`).
- Example testspec writing an identification string: `testspecs/test_registry.yaml:9`.

