import sys

with open('tests/test_api.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if 394 <= i <= 399:
        if i == 394:
            new_lines.append('    for strategy in ("baseline", "collectionRules", "ai"):\n')
            new_lines.append('        for metric in ("amountRecovered", "recoveryRate", "recoveryPerAction", "customersTargeted"):\n')
            new_lines.append('            assert set(result["strategies"][strategy][metric]) == {"mean", "median", "min", "max", "standardDeviation"}\n')
            new_lines.append('            \n')
            new_lines.append('    assert set(result["uplift"]) == {"rules_vs_baseline", "ai_vs_baseline", "ai_vs_rules"}\n')
            new_lines.append('    for comparison in ("rules_vs_baseline", "ai_vs_baseline", "ai_vs_rules"):\n')
            new_lines.append('        assert set(result["uplift"][comparison]) == {"amount", "rate", "recoveryRateDelta"}\n')
            new_lines.append('        for metric in ("amount", "rate", "recoveryRateDelta"):\n')
            new_lines.append('            assert set(result["uplift"][comparison][metric]) == {"mean", "median", "min", "max", "standardDeviation"}\n')
        continue
    new_lines.append(line)

with open('tests/test_api.py', 'w') as f:
    f.writelines(new_lines)
