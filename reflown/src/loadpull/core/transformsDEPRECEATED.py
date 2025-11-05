

    # Eq. 3 from user-provided reference (load reflection from port-2 receiver)
    # Gamma_L = e23 + (e22 * e24 * TEST2/REF2) / (1 - e21 * TEST2/REF2)
    # Mapped to available keys:
    #   TEST2/REF2 -> b2/a2 from wave_values
    #   e22e24 -> tracking_output
    #   e22 -> refltrack_output
    #   e21 -> srcmatch_output
    #   e24 -> loadmatch_output (defaults to 1 if missing)
    # def ab2gamma(T,R,directivity,tracking,port_match):
    #     # eq from hackborn. extrapolated equation 
    #     return directivity + (tracking*T/R)/(1-port_match*T/R)
    def eq3_gammaL(payload: dict, cal: dict) -> dict:
        
        # Port selection: 'output' (b2/a2) or 'input' (b1/a1)
        raw_port = payload.get('port', 'output')
        port = str(raw_port).strip().lower()
        # Accept common synonyms
        err = cal.get("error_terms") or {}
        if port in ('out', 'load', 'port2', 'p2', '2', 'output'):
            e22e24 = _extract_array_field(err, ["transtrack_output2input"], dtype=complex)
            e23 = _extract_array_field(err, ["directivity_output"], dtype=complex)
            e21 = _extract_array_field(err, ["srcmatch_output"], dtype=complex)
        if port in ('in', 'source', 'port1', 'p1', '1','input'):
            e22e24 = _extract_array_field(err, ["transtrack_input2output"], dtype=complex)
            e23 = _extract_array_field(err, ["directivity_input"], dtype=complex)
            e21 = _extract_array_field(err, ["srcmatch_input"], dtype=complex)

        wv = payload.get("wave_data") or payload
        # b2/a2 ratio across frequency
        b2 = _extract_array_field(wv, ["b2", "B2"], dtype=complex)
        a2 = _extract_array_field(wv, ["a2", "A2"], dtype=complex)

        if b2 is None or a2 is None:
            return {}
        b2 = np.asarray(b2, dtype=complex)
        a2 = np.asarray(a2, dtype=complex)
        # Guard against divide-by-zero

        #whether a or b is test or ref needs to be double checked
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(a2 != 0, a2 / b2, 0.0 + 0.0j)
       
        # Coerce to arrays, provide sane defaults
        def _as_arr(x, default=0.0+0.0j):
            if x is None:
                return np.full_like(ratio, fill_value=default, dtype=complex)
            return np.asarray(x, dtype=complex)

        e22e24a = _as_arr(e22e24, 0.0+0.0j)
        e23a = _as_arr(e23, 1.0+0.0j)  # reflection tracking as gain term
        e21a = _as_arr(e21, 0.0+0.0j)

        # Vectorized Eq. 3
        num = e22e24a * ratio
        den = 1.0 - e21a * ratio
        with np.errstate(divide="ignore", invalid="ignore"):
            gammaL = e23a + np.where(den != 0, num / den, np.nan+0.0j)

        return {
            "gamma_L": {
                "real": gammaL.real.tolist(),
                "imag": gammaL.imag.tolist(),
                "mag": np.abs(gammaL).tolist(),
                "deg": np.degrees(np.angle(gammaL)).tolist(),
            },
            "ratio_b2_over_a2": {
                "real": ratio.real.tolist(),
                "imag": ratio.imag.tolist(),
            },
        }

    # Single-point Eq.3 gamma correction (by frequency)
    def eq3_gammaL_single(payload: dict, cal: dict) -> dict:

        # Port selection: 'output' (b2/a2) or 'input' (b1/a1)
        raw_port = payload.get('port', 'output')
        port = str(raw_port).strip().lower()
        # Accept common synonyms
        if port in ('out', 'load', 'port2', 'p2', '2'):
            port = 'output'
        if port in ('in', 'source', 'port1', 'p1', '1'):
            port = 'input'
        # Frequency selection: prefer Hz; else accept GHz under keys freq_ghz/frequency
        def _to_float(x):
            try:
                return float(x)
            except Exception:
                return None

        freq_hz = _to_float(payload.get('freq_hz') or payload.get('frequency_hz'))
        if freq_hz is None:
            ghz = _to_float(payload.get('freq_ghz') or payload.get('frequency'))
            # print(breakhere)
            if ghz is not None:
                freq_hz = ghz * 1e9
        if freq_hz is None:
            return {}

        # Wave data: can be nested or flat
        wv = payload.get('wave_data') or payload
        # Frequency vector from wave data, if present
        wv_freq = _extract_frequency_vector(wv)
        # print(breakhere)
        # Choose wave keys by port
        if port == 'output':
            b_keys, a_keys = ['b2', 'B2'], ['a2', 'A2']
        else:
            b_keys, a_keys = ['b1', 'B1'], ['a1', 'A1']

        b_arr = _extract_array_field(wv, b_keys, dtype=complex)
        a_arr = _extract_array_field(wv, a_keys, dtype=complex)
        if b_arr is None or a_arr is None:
            return {}

        b_flat = np.asarray(b_arr, dtype=complex).ravel()
        a_flat = np.asarray(a_arr, dtype=complex).ravel()

        if wv_freq is not None and wv_freq.size > 0:
            idx_w = int(np.argmin(np.abs(wv_freq - freq_hz)))
            idx_w = min(idx_w, b_flat.size - 1, a_flat.size - 1)
        else:
            idx_w = 0

        b = b_flat[idx_w]
        a = a_flat[idx_w]
        ratio = (a / b) if a != 0 else 0.0 + 0.0j #its a/b just leave it 

        # Error terms from calibration store
        err = cal.get('error_terms') or {}
        err_freq = _extract_frequency_vector(err.get('freq'))
        idx_e = 0
        if err_freq is not None and err_freq.size > 0:
            idx_e = int(np.argmin(np.abs(err_freq - freq_hz)))

        def _term_at(key: str, default: complex) -> complex:
            arr = _extract_array_field(err, [key], dtype=complex)
            if arr is None:
                return default
            flat = np.asarray(arr, dtype=complex).ravel()
            return flat[min(idx_e, flat.size - 1)]

        if port == 'output':
            e22e24 = _term_at('transtrack_output2input', 0.0 + 0.0j)
            e23 = _term_at('directivity_output',   1.0 + 0.0j)
            e21 = _term_at('srcmatch_output',    0.0 + 0.0j)
            eR = _term_at('refltrack_output',    0.0 + 0.0j)
            
        else:
            e22e24 = _term_at('transtrack_input2output', 0.0 + 0.0j)
            e23 = _term_at('directivity_input',   1.0 + 0.0j)
            e21 = _term_at('srcmatch_input',    0.0 + 0.0j)

        num = eR * ratio
        den = 1.0 - e21 * ratio
        g = (e23 + num / den if den != 0 else np.nan + 0.0j)

        return {
            'gamma_L': {
                'real': float(np.real(g)),
                'imag': float(np.imag(g)),
                'mag':  float(np.abs(g)),
                'deg':  float(np.degrees(np.angle(g))),
            },
            'freq_hz': float(freq_hz),
        }

    registry.register("eq3_gammaL", eq3_gammaL)
    registry.register("eq3_gammaL_single", eq3_gammaL_single)
