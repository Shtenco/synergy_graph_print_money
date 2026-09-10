# Synthetic regression history

These CSV files preserve the numerical V3–V6 experiments developed before V7 live Base validation. They are regression/reference artifacts, not forecasts or realized returns.

Important: V5 demonstrated the value of concentrating liquidity in the simulated route, but its interpretation of atomic self-owned LP as a conversion layer was corrected in V6. A self-swap through a 100%-owned LP does not create external HardNAV when router + LP are consolidated. V6/V7 require external value transfer through foreign pools or genuine external demand for RUBC/RUBX.
