# Raw review prompts: operating-change what-if

These are the two review messages supplied in the project conversation that scoped and checked the optional what-if command. They are preserved verbatim as user-provided review text; this file does not claim that the review text is a full export of the Claude or Codex conversation.

## Follow-up review and checklist

> The what-if closes the "simulate operating changes" gap in a way you can defend. It reuses the solver, stores each run with its input config and hash, and its scope is stated honestly (one line, one parameter). I haven't seen the code or the commit, so this is based on your summary.
>
> ## The results hang together
>
> - Closing the valve to 80% raises the valve's resistance, so flow drops and the pump moves back up its curve. Discharge pressure rises, matching the partial-valve signature from your earlier sweep.
> - The source ends higher and the destination lower than baseline, as expected when less water is transferred.
> - The two level shifts are equal (about 0.067 m each), which implies the two tanks have equal areas.
>
> ## One check to run: level change versus volume
>
> Volume not transferred ≈ 5.60 m³/h × 24 h ≈ 134 m³. So the level shift should be about 134 m³ divided by the tank area. At 0.067 m, that implies roughly 2,000 m². Compare that with the tank area in the one-line configuration. If the areas differ materially, either the summary reports something other than what I'm assuming (for example the mean flow difference includes a changing head effect), or there's a bookkeeping slip. If they agree, add that check as a test (`Δlevel × area ≈ Δvolume transferred`), since it ties the summary numbers to the mass balance. Remember the mean flow difference is itself an average over a changing static head, so expect agreement within a small tolerance rather than exactly.
>
> ## Make sure the docs now agree with the code
>
> The what-if changes statements that were true earlier. Check for contradictions:
>
> - `README.md`: the "Not implemented" list shouldn't still say operating changes aren't simulated. Reword it to "facility-wide demand schedules, mode transitions and multi-parameter changes are not simulated".
> - `DESIGN.md`: the scope and limitations sections need the same update, plus a line on why the what-if is single-line (reuses the validated solver, keeps the full generator's hashes unchanged).
> - `AI_USAGE.md`, `DEVLOG.md`, the prompt history and `WALKTHROUGH.md`: add the what-if, and say who proposed it and what you reviewed.
> - `data_dictionary.md`: say whether the what-if's `SimulationRun` records follow the same schema, and whether they land in the main dataset or only in `what-if-output`.
>
> ## Small questions to settle
>
> - **ID collisions:** make sure what-if run IDs can't collide with the generator's `SIM-2026-NNNNNN` series, or that they live in a separate output folder and are documented as such.
> - **Determinism:** the what-if has no randomness, so two runs should produce identical files. A test that runs it twice and compares hashes would fit your existing approach, if one of the three new tests isn't already doing that.
> - **Output folder:** decide whether `what-if-output/` is git-ignored or whether a small example output is committed. A committed example lets reviewers see the result without running anything.
> - **Input validation:** check that the command rejects out-of-range openings (negative, above 1, or a fully closed valve) with a clear message rather than a solver error.
>
> ## Where you stand
>
> Implementation is complete, including the optional what-if. Remaining work is documentation consistency and the things only you can do:
>
> 1. Reconcile the docs with the what-if (list above), then push.
> 2. Add the raw prompt transcripts under `docs/prompt_history/raw/`.
> 3. Read `AI_USAGE.md` once and edit anything you wouldn't say aloud.
> 4. Rehearse the walkthrough, including the what-if: why one parameter on one line, what the numbers show, and what you'd extend next (pump speed, demand changes, facility-wide scenarios).
> 5. Final check: open the repo logged out, clone it fresh, and run the README commands including the what-if.
>
> The static report and CI are now optional extras. I'd skip them unless everything above is finished.

## Initial implementation suggestion

> ### If you want to close the operating-change gap
>
> A small `what-if` command would do it: take a parameter such as a valve opening or pump speed, re-run the solver with that change, store it as a `SimulationRun` with its input config, and report the deltas in flow, pressure and tank levels. Your solver already supports it, so it’s mostly a thin wrapper plus tests. It’s optional. Only do it if you can finish it with tests and a README update, without breaking the reproducibility hashes. If you don’t, be ready to explain why you left it out and what you’d build first.
