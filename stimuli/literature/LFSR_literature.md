### Literature Overview and Mapping

The following documents cover complementary aspects of bounded LFSR–based
constrained-random stimulus generation. Each file informs a distinct part of
the system architecture shown in the schematic.

- **`random-number-generation-*.pdf`**  
  Provides background on hardware-oriented random number generators, including
  LFSRs and related constructions. This material informs the design of the core
  random source used in the Stimuli RTL.

- **`handstat2.pdf`**  
  Focuses on statistical analysis and validation of pseudo-random sequences.
  This reference is used to reason about distribution bias and statistical
  properties introduced by bounded mappings (e.g., range reduction or rejection)
  applied to LFSR outputs in the Stimuli RTL.

- **`pal-et-al-2024-hardware-accelerated-*.pdf`**  
  Describes hardware-accelerated constrained-random test generation techniques.
  This work motivates pushing random value selection and partial constraint
  handling into synthesizable logic, influencing the design of the Parser and
  Stimuli RTL blocks.

- **`coverage-driven-distribution-*.pdf`**  
  Covers coverage-driven stimulus distribution and feedback mechanisms.
  This material informs the interaction between Coverage RTL and Stimuli RTL,
  where coverage information may be used to bias or guide random stimulus
  generation.