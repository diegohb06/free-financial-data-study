You are answering factual questions about the financial statements of US public companies. Each question has one correct numeric answer taken from the companies' SEC filings.

Read the questions from this file: {QUESTIONS_FILE}

Tools and data you may use: {TOOLS}

Rules:

- This is a self-contained task. Do not read any other files on this machine (project folders, documentation, other directories), and do not use any tool or data source other than those allowed above. Reading the questions file and writing the answers file is always allowed.
- Read each question carefully: the period, the exact definition asked for, and whether it asks for a figure as first reported, as most recently reported, or as known on a particular date.
- Give your best answer as a single number. Dollar amounts in whole US dollars (for example 394328000000, not 394.3 billion). Percentages as a number with two decimals (for example 12.34).
- If you cannot find or work out an answer you trust with the allowed tools, give null rather than inventing a number.
- Work through all the questions. Do not ask for clarification.

When finished, write your answers to {ANSWERS_FILE} as a JSON list with one object per question, like this:

[{"id": "Q01", "answer": 123456000, "source": "where the number came from (URL, or file and field, or filing)", "note": "one sentence on the definition, period and version you used"}]

Then reply with the same JSON and nothing else.
