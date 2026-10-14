(function () {
  const FIXTURES = [
    ["raw_statement.csv", "rawStatementCsv"],
    ["statement_meta.json", "statementMetaJson"],
    ["chart_of_accounts.csv", "chartOfAccountsCsv"],
    ["reference.csv", "referenceCsv"],
    ["entity_map.csv", "entityMapCsv"],
  ];

  const COLUMNS = [
    "Cardholder Name",
    "Transaction Date",
    "Post Date",
    "Description",
    "Extended Details",
    "Amount",
    "Type",
    "Country",
    "Reference Number",
  ];

  const MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  const state = {
    step: "load",
    source: "",
    label: "",
    statementCsv: "",
    fixtures: null,
    result: null,
  };

  const loadError = document.getElementById("load-error");
  const runError = document.getElementById("run-error");
  const loadButton = document.getElementById("load-sample");
  const fileInput = document.getElementById("statement-file");

  let fixturePromise = null;

  function loadFixtures() {
    if (!fixturePromise) {
      fixturePromise = Promise.all(
        FIXTURES.map(function (pair) {
          return fetch("fixtures/" + pair[0]).then(function (res) {
            if (!res.ok) throw new Error("missing " + pair[0]);
            return res.text().then(function (text) {
              return [pair[1], text];
            });
          });
        })
      ).then(function (pairs) {
        const files = {};
        pairs.forEach(function (pair) {
          files[pair[0]] = pair[1];
        });
        return files;
      }).catch(function (err) {
        fixturePromise = null;
        throw err;
      });
    }
    return fixturePromise;
  }

  function showError(node, message) {
    node.hidden = !message;
    node.textContent = message || "";
  }

  function setStep(step) {
    state.step = step;
    ["load", "run", "results"].forEach(function (name) {
      const panel = document.getElementById("panel-" + name);
      const crumb = document.getElementById("crumb-" + name);
      const on = name === step;
      panel.hidden = !on;
      crumb.classList.toggle("is-current", on);
      crumb.classList.toggle("is-done", stepIndex(name) < stepIndex(step));
      if (on) crumb.setAttribute("aria-current", "step");
      else crumb.removeAttribute("aria-current");
    });
    const heading = document.querySelector("#panel-" + step + " .step-line");
    if (heading) heading.focus();
  }

  function stepIndex(name) {
    return { load: 0, run: 1, results: 2 }[name];
  }

  function missingColumns(csvText) {
    const rows = CCPipeline.parseCsv(csvText);
    if (!rows.length) return { rows: rows, missing: ["the file has no data rows"] };
    const keys = Object.keys(rows[0]);
    const missing = COLUMNS.filter(function (name) {
      return keys.indexOf(name) === -1;
    });
    return { rows: rows, missing: missing };
  }

  function formatPeriod(period) {
    const match = /^(\d{4})-(\d{2})$/.exec(period || "");
    if (!match) return period || "";
    const month = MONTHS[Number(match[2]) - 1];
    return month ? month + " " + match[1] : period;
  }

  function money(amount) {
    const sign = amount < 0 ? "-" : "";
    return sign + "$" + Math.abs(amount).toLocaleString("en-US");
  }

  function usDate(iso) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return iso || "";
    return iso.slice(5, 7) + "/" + iso.slice(8, 10) + "/" + iso.slice(0, 4);
  }

  function accountName(code, coa) {
    for (let i = 0; i < coa.length; i++) {
      if (coa[i].gl_code === code) return code + " " + coa[i].name;
    }
    return code;
  }

  function sourceLabel(source) {
    if (source === "reference") return "Saved match";
    if (source === "coa") return "Account list";
    return source;
  }

  function reviewReason(row) {
    if (row.coding_source === "no_gl") return "No account matched this merchant. It was not guessed.";
    if (row.coding_source === "ambiguous_coa") return "More than one account matched. A person needs to pick one.";
    if (row.coding_source === "reference_gl_not_on_coa") {
      return "The saved account is not on the chart. A person needs to recode it.";
    }
    return row.review_reason;
  }

  function el(tag, props, children) {
    const node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (key) {
        if (key === "className") node.className = props[key];
        else if (key === "text") node.textContent = props[key];
        else node.setAttribute(key, props[key]);
      });
    }
    (children || []).forEach(function (child) {
      if (child == null || child === false) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function stat(label, value, caption) {
    const parts = [
      el("p", { className: "label", text: label }),
      el("p", { className: "value", text: value }),
    ];
    if (caption) parts.push(el("p", { className: "caption", text: caption }));
    return el("div", null, parts);
  }

  function differenceCaption(result) {
    const rec = result.reconciliation;
    let paymentSum = 0;
    let thankYou = false;
    for (let i = 0; i < result.droppedPayments.length; i++) {
      const row = result.droppedPayments[i];
      paymentSum += row.amount;
      if (row.row_class === "PAYMENT" || /thank\s+you/i.test(row.description_raw || "")) thankYou = true;
    }
    if (thankYou && rec.variance_vs_statement !== 0 && rec.variance_vs_statement === -paymentSum) {
      return "Thank-you card payment dropped in cleaning. Not missing money.";
    }
    return "Cleaned total minus the statement total. Not missing money.";
  }

  function makeTable(headers, records) {
    const head = el("tr", null, headers.map(function (header) {
      return el("th", { scope: "col", className: header.num ? "num" : "", text: header.label });
    }));
    const body = el("tbody", null, records.map(function (record) {
      return el("tr", null, record.map(function (cell, index) {
        return el("td", { className: headers[index].num ? "num" : "", text: cell });
      }));
    }));
    return el("div", { className: "table-wrap" }, [
      el("table", null, [el("thead", null, [head]), body]),
    ]);
  }

  function showLoaded(rowCount) {
    const facts = document.getElementById("loaded-facts");
    const note = document.getElementById("run-note");
    facts.replaceChildren();
    const meta = JSON.parse(state.fixtures.statementMetaJson);
    const period = formatPeriod(String(meta.period || ""));
    [
      ["Statement", state.label],
      ["Rows in the file", String(rowCount)],
      ["Statement total", money(Number(meta.reported_activity) || 0) + " (sample, " + period + ")"],
    ].forEach(function (pair) {
      facts.appendChild(el("dt", { text: pair[0] }));
      facts.appendChild(el("dd", { text: pair[1] }));
    });
    note.textContent = state.source === "sample"
      ? "Accounts, companies, and saved merchants all come from the sample files."
      : "Accounts, companies, and saved merchants still come from the sample files. The statement total above is the sample figure too.";
  }

  function goToRun(csvText, source, label) {
    const checked = missingColumns(csvText);
    if (checked.missing.length) {
      fileInput.value = "";
      const problem = checked.missing[0] === "the file has no data rows"
        ? "That file has no statement rows."
        : "This CSV is missing columns: " + checked.missing.join(", ") + ".";
      showError(loadError, problem);
      return;
    }
    state.source = source;
    state.label = label;
    state.statementCsv = csvText;
    state.result = null;
    showError(loadError, "");
    showError(runError, "");
    showLoaded(checked.rows.length);
    setStep("run");
  }

  function plainError(err) {
    const message = err && err.message ? err.message : "The statement could not be coded.";
    const row = /^Row (\d+):/.exec(message);
    const where = row ? "Row " + row[1] + ": " : "";
    if (message.indexOf("non-whole-dollar") !== -1) {
      const amount = /not allowed: (.*)$/.exec(message);
      return where + (amount ? amount[1] : "That amount") + " is not a whole dollar. Use a number like 1000.";
    }
    if (message.indexOf("unrecognized date") !== -1) {
      const date = /unrecognized date: (.*)$/.exec(message);
      return where + (date ? date[1] : "That date") + " is not a date I can read. Use a date like 03/02/2026.";
    }
    if (message.indexOf("invalid amount") !== -1 || message.indexOf("empty amount") !== -1) {
      return where + "the amount is empty or not a number. Use a whole dollar amount like 1000.";
    }
    return message;
  }

  function renderResults(result) {
    const summary = document.getElementById("summary");
    const detail = document.getElementById("detail");
    const rec = result.reconciliation;
    const journalCount = Object.keys(result.journals).length;

    summary.replaceChildren(
      el("div", { className: "stats" }, [
        stat("Coded", String(result.coded.length)),
        stat("Needs review", String(result.review.length)),
        stat("Journals", String(journalCount)),
        stat("Difference", money(rec.variance_vs_statement), differenceCaption(result)),
      ])
    );

    detail.replaceChildren();

    const reviewBlock = el("section", { className: "block" });
    reviewBlock.appendChild(el("h2", { className: "block-title", text: "Flagged for a person" }));
    if (!result.review.length) {
      reviewBlock.appendChild(el("p", { className: "section-note", text: "The tool did not flag any charges." }));
    } else {
      const waiting = result.review.length === 1
        ? "The tool flagged 1 charge. A person approves or edits it before it is final."
        : "The tool flagged " + result.review.length + " charges. A person approves or edits them before they are final.";
      reviewBlock.appendChild(el("p", {
        className: "section-note",
        text: waiting,
      }));
      reviewBlock.appendChild(makeTable(
        [
          { label: "Date" },
          { label: "Person" },
          { label: "Company" },
          { label: "Merchant" },
          { label: "Amount", num: true },
          { label: "Why" },
        ],
        result.review.map(function (row) {
          return [
            usDate(row.txn_date),
            row.cardholder_first,
            row.entity || "No company",
            row.appears_as,
            money(row.amount),
            reviewReason(row),
          ];
        })
      ));
    }
    detail.appendChild(reviewBlock);

    const journalBlock = el("section", { className: "block" });
    journalBlock.appendChild(el("h2", { className: "block-title", text: "Journals" }));
    let journalNote = "Flagged rows stay out of the journals until a person approves or edits them. Company totals further down still include them.";
    if (result.unmapped.length) {
      const rows = result.unmapped.length === 1 ? "1 row has" : result.unmapped.length + " rows have";
      journalNote += " " + rows + " no company on the sample list, so " +
        (result.unmapped.length === 1 ? "it is" : "they are") + " not in a journal.";
    }
    journalBlock.appendChild(el("p", { className: "section-note", text: journalNote }));
    if (!journalCount) {
      journalBlock.appendChild(el("p", {
        className: "section-note",
        text: "No journals. None of these people are on the sample company list.",
      }));
    }
    Object.keys(result.journals).sort().forEach(function (entity) {
      const journal = result.journals[entity];
      const block = el("div", { className: "journal" });
      block.appendChild(el("h3", { text: entity }));
      let balance = "Debits " + money(journal.debit_total) + ". Credits " + money(journal.credit_total) + ". Balanced.";
      if (journal.excluded_review_amount) {
        balance += " " + money(journal.excluded_review_amount) + " is flagged for a person and is not in this journal.";
      }
      block.appendChild(el("p", { className: "balance", text: balance }));
      block.appendChild(makeTable(
        [
          { label: "Account" },
          { label: "Debit", num: true },
          { label: "Credit", num: true },
          { label: "Description" },
        ],
        journal.lines.map(function (line) {
          return [
            accountName(line.gl_code, result.coa),
            line.debit ? money(line.debit) : "",
            line.credit ? money(line.credit) : "",
            line.description,
          ];
        })
      ));
      journalBlock.appendChild(block);
    });
    detail.appendChild(journalBlock);

    const recon = el("section", { className: "block" });
    recon.appendChild(el("h2", { className: "block-title", text: "Totals" }));
    const paymentBits = result.droppedPayments.map(function (row) {
      return row.appears_as + " (" + money(Math.abs(row.amount)) + ")";
    });
    const paymentSum = result.droppedPayments.reduce(function (sum, row) {
      return sum + row.amount;
    }, 0);
    let varianceText;
    if (state.source === "sample") {
      varianceText = "Cleaned charges total " + money(rec.cleaned_activity) +
        ". The statement total is " + money(rec.reported_activity) +
        ". The difference is " + money(rec.variance_vs_statement) + ".";
      if (paymentBits.length && rec.variance_vs_statement === -paymentSum) {
        varianceText += " " + (paymentBits.length === 1 ? "A card payment was" : "Card payments were") +
          " dropped: " + paymentBits.join(", ") +
          ". That is the difference. It is left as-is.";
      }
    } else {
      varianceText = "Cleaned charges total " + money(rec.cleaned_activity) +
        ". The statement total shown here is still the sample figure, " + money(rec.reported_activity) +
        ", so the difference only means something for the sample statement.";
    }
    recon.appendChild(el("p", { className: "section-note", text: varianceText }));
    const nets = Object.keys(rec.entity_nets);
    recon.appendChild(makeTable(
      [{ label: "Company" }, { label: "Total, including rows in review", num: true }],
      nets.map(function (name) {
        return [name, money(rec.entity_nets[name])];
      })
    ));
    detail.appendChild(recon);

    const coded = el("section", { className: "block" });
    coded.appendChild(el("h2", { className: "block-title", text: "Coded charges" }));
    if (!result.coded.length) {
      coded.appendChild(el("p", { className: "section-note", text: "Nothing was coded." }));
      detail.appendChild(coded);
      return;
    }
    coded.appendChild(makeTable(
      [
        { label: "Date" },
        { label: "Person" },
        { label: "Company" },
        { label: "Merchant" },
        { label: "Account" },
        { label: "Amount", num: true },
        { label: "From" },
      ],
      result.coded.map(function (row) {
        return [
          usDate(row.txn_date),
          row.cardholder_first,
          row.entity || "No company",
          row.appears_as,
          row.gl_code + " " + row.gl_name,
          money(row.amount),
          sourceLabel(row.coding_source),
        ];
      })
    ));
    detail.appendChild(coded);
  }

  function resetToLoad() {
    state.source = "";
    state.label = "";
    state.statementCsv = "";
    state.result = null;
    fileInput.value = "";
    showError(loadError, "");
    showError(runError, "");
    setStep("load");
  }

  loadButton.addEventListener("click", function () {
    showError(loadError, "");
    loadButton.disabled = true;
    loadButton.textContent = "Loading sample...";
    loadFixtures().then(function (files) {
      state.fixtures = files;
      goToRun(files.rawStatementCsv, "sample", "Sample statement");
    }).catch(function () {
      showError(loadError, "The sample files did not load. Refresh the page and try again.");
    }).finally(function () {
      loadButton.disabled = false;
      loadButton.textContent = "Load sample statement";
    });
  });

  fileInput.addEventListener("change", function () {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    showError(loadError, "");
    const reader = new FileReader();
    reader.onload = function () {
      loadFixtures().then(function (files) {
        state.fixtures = files;
        goToRun(String(reader.result || ""), "upload", file.name);
      }).catch(function () {
        showError(loadError, "The sample chart and company list did not load. Refresh the page and try again.");
      });
    };
    reader.onerror = function () {
      showError(loadError, "That file could not be read.");
    };
    reader.readAsText(file);
  });

  document.getElementById("run-coding").addEventListener("click", function () {
    showError(runError, "");
    try {
      const result = CCPipeline.runPipeline({
        rawStatementCsv: state.statementCsv,
        statementMetaJson: state.fixtures.statementMetaJson,
        chartOfAccountsCsv: state.fixtures.chartOfAccountsCsv,
        referenceCsv: state.fixtures.referenceCsv,
        entityMapCsv: state.fixtures.entityMapCsv,
      });
      state.result = result;
      renderResults(result);
      setStep("results");
    } catch (err) {
      showError(runError, plainError(err));
    }
  });

  document.getElementById("download-all").addEventListener("click", function () {
    if (!state.result) return;
    const files = CCPipeline.renderOutputs(state.result);
    const zip = CCPipeline.buildZip(files);
    const blob = new Blob([zip], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "expense-coding.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  });

  document.getElementById("back-to-load").addEventListener("click", resetToLoad);
  document.getElementById("start-over").addEventListener("click", resetToLoad);
})();
