# Loadpull CLI (SCPI, JSON)


### Quickstart


```bash
pip install -e .
loadpull list-tests
loadpull run testspecs/power_sweep.yaml --bench benches/bench_default.toml --out runs/$(date +%F_%H%M)
```
## Instruments, Transports, and YAML Workflow

```
+---------------------------+
|      Testspec YAML        |
|  (defines steps, sweeps)  |
+-------------+-------------+
              |
              v
+---------------------------+
|       Sequencer           |
| (_run_actions, Context)   |
+-------------+-------------+
              |
              v
+---------------------------+
|   Instrument Driver       |
| (KeysightPNA, RSZVA, ...) |
+-------------+-------------+
              |
              v
+---------------------------+
|         SCPI Core         |
| (write/query, error poll) |
+-------------+-------------+
              |
              v
+---------------------------+
|        Transport          |
|  (Socket, GPIB, Fake)     |
+-------------+-------------+
              |
              v
+---------------------------+
|    Physical Instrument    |
+---------------------------+
```


This scaffold separates **how instruments communicate** from **what commands they provide**. The layers are:

1. **Transport** – the raw I/O channel (e.g. TCP socket, GPIB via PyVISA, fake transport for testing).

   * Examples:
    this
     * `SocketTransport("192.168.0.20", 5025)` → LAN SCPI over sockets.
     * `VisaGPIBTransport("GPIB0::8::INSTR")` → GPIB via PyVISA.

2. **SCPI Wrapper** – wraps a transport with `.write(cmd)` and `.query(cmd?)` methods and optional error polling.

3. **Instrument Driver** – a thin class specific to an instrument family (Keysight PNA, R&S ZVA, etc.).

   * Each method translates a semantic action into one or more SCPI commands.
   * Example:

     ```python
     class KeysightPNA(Instrument):
         def set_power(self, p_dbm: float) -> str:
             self.scpi.write(f"SOUR:POW {p_dbm}DBM")
             return "OK"
     ```

4. **Instrument Registry** – a dictionary mapping short names (e.g. `"PNA"`, `"ZVA"`) to driver classes.

   ```python
   INSTRUMENTS = {
       "PNA": KeysightPNA,
       "ZVA": RSZVA,
   }
   ```

5. **Context** – when a test run begins, the bench file (TOML) is parsed, transports are created, SCPI wrappers are initialized, and each instrument driver is constructed.

   ```python
   instruments = {
       "PNA": KeysightPNA(sess.new_scpi("PNA")),
       "ZVA": RSZVA(sess.new_scpi("ZVA")),
   }
   ctx = Context(instruments=instruments, writer=writer)
   ```

6. **Sequencing** – the YAML testspec uses `inst:` fields that match the registry keys. At runtime, the sequence runner looks up the right instrument object and calls the specified method.

---

## Example Workflow

1. **Define instruments in a bench file** (`benches/lab.toml`):

   ```toml
   [visa]
   PNA = "192.168.0.20:5025"
   ZVA = "GPIB0::8::INSTR"
   ```

2. **Add or extend drivers** in `src/loadpull/instruments/`:

   ```python
   class RSZVA(Instrument):
       def preset(self) -> str:
           self.scpi.write("SYST:PRES")
           return "OK"
   ```

3. **Register the driver** in `core/registry.py`:

   ```python
   INSTRUMENTS = {
       "PNA": KeysightPNA,
       "ZVA": RSZVA,
   }
   ```

4. **Use it in a testspec YAML** (`testspecs/pna_zva_example.yaml`):

   ```yaml
   name: pna_zva_test
   requires: [PNA, ZVA]

   steps:
     - call: {inst: PNA, method: preset}
     - call: {inst: ZVA, method: preset}
     - call: {inst: PNA, method: set_power, args: [-10]}
     - measure: {inst: ZVA, method: capture_point, save_as: sparams}
   ```

5. **Run it**:

   ```bash
   loadpull run testspecs/pna_zva_example.yaml --bench benches/lab.toml --out runs/$(date +%F_%H%M)
   ```

---

# Calibration

## Calibration

- https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=278582
- Add a `calibrate` step to any testspec to run instrument setup once and store the result under a named key (e.g. `tuner_offset`).
- Calibration values are persisted in `calibration/<bench_name>.json`, keyed by bench; later runs load them automatically and expose them as `${cal.<name>}` in substitutions.
- Set `force: true` on a `calibrate` action when you need to re-measure even if a cached value exists. Prior values are archived with timestamps for traceability.

Example snippet:

```yaml
steps:
  - calibrate:
      name: tuner_offset
      do:
        - measure: {inst: DMM1, method: read_voltage, save_as: offset}
      save: "${offset}"
  - call: {inst: Tuner, method: move_to_offset, args: ["${cal.tuner_offset}"]}
```
