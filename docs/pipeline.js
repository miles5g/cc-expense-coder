/* Browser port of the Python pipeline (clean -> split -> code -> finalize -> journal).
   renderOutputs() is what the page puts in the download. Keep it byte-for-byte
   with `python3 -m cc_coder` on the same fixtures. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.CCPipeline = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const TXN_FIELDS = [
    "txn_id",
    "cardholder_raw",
    "cardholder_first",
    "txn_date",
    "post_date",
    "description_raw",
    "extended_details",
    "appears_as",
    "amount",
    "txn_type",
    "country_raw",
    "country",
    "reference_number",
    "row_class",
    "entity",
    "merchant_key",
    "gl_code",
    "gl_name",
    "coding_source",
    "confidence",
    "review_reason",
    "origin_kept",
  ];

  const JOURNAL_FIELDS = ["GL Code", "Debit", "Credit", "Description"];

  const PAYMENT_THANK_YOU =
    /(online\s+payment.*thank\s+you)|(payment\s+thank\s+you)|(thank\s+you\s+for\s+(your\s+)?payment)|(autopay\s+payment)|(payment\s+received\s+thank\s+you)/i;
  const PROCESSOR_PREFIX = /^(sq\s*\*|tst\s*\*|paypal\s*\*|spp\s*\*|pos\s*\*)\s*/i;
  const TRAILING_LOCATION =
    /\s+\d{5}(?:-\d{4})?$|\s+[A-Z]{2}$|\s+(united\s+states|usa|us)$/i;
  const STORE_NUMBER = /\s+#?\d{3,}$/;
  const GENERIC_PREFIX = /^(purchase|pos|sale)(\s+authorized)?(\s+on\s+\d|\/)/i;
  const TRAILING_STAR_CODE = /\*+[A-Z0-9]+$/i;

  const COUNTRY_ALIASES = {
    US: "UNITED STATES",
    USA: "UNITED STATES",
    "U.S.": "UNITED STATES",
    "U.S.A.": "UNITED STATES",
    "U.S.A": "UNITED STATES",
    "UNITED STATES OF AMERICA": "UNITED STATES",
    "UNITED STATES": "UNITED STATES",
  };

  const MERCHANT_ALIASES = {
    "amazon.com": "amazon",
    amzn: "amazon",
    "amazon mktplace": "amazon",
    "amazon marketplace": "amazon",
    "uber trip": "uber",
    "uber *trip": "uber",
    "starbucks store": "starbucks",
  };

  const PUBLIC_MERCHANT_ROOTS = { amazon: true, uber: true, starbucks: true };

  const VARIANCE_NOTE =
    "Variance is reported, not forced. Payment thank-you rows are excluded from the coding population; issuer-reported activity may still include them.";

  function collapse(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function isAsciiLetter(ch) {
    return (ch >= "A" && ch <= "Z") || (ch >= "a" && ch <= "z");
  }

  function isPyUpper(text) {
    let any = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (!isAsciiLetter(ch)) continue;
      any = true;
      if (ch !== ch.toUpperCase()) return false;
    }
    return any;
  }

  function isPyLower(text) {
    let any = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (!isAsciiLetter(ch)) continue;
      any = true;
      if (ch !== ch.toLowerCase()) return false;
    }
    return any;
  }

  function pyTitle(text) {
    let out = "";
    let prevCased = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (isAsciiLetter(ch)) {
        out += prevCased ? ch.toLowerCase() : ch.toUpperCase();
        prevCased = true;
      } else {
        out += ch;
        prevCased = false;
      }
    }
    return out;
  }

  function titleMerchant(appearsAs) {
    const text = collapse(appearsAs || "");
    if (!text) return "";
    if (isPyUpper(text) || isPyLower(text)) return pyTitle(text);
    return text;
  }

  function parseAmount(raw) {
    let text = String(raw == null ? "" : raw).trim();
    if (!text) throw new Error("empty amount");
    let negative = false;
    if (text.startsWith("(") && text.endsWith(")")) {
      negative = true;
      text = text.slice(1, -1);
    }
    text = text.replace(/\$/g, "").replace(/,/g, "").replace(/ /g, "");
    if (text.startsWith("-")) {
      negative = true;
      text = text.slice(1);
    }
    if (text.startsWith("+")) text = text.slice(1);
    if (text.indexOf(".") !== -1) {
      const dot = text.indexOf(".");
      const whole = text.slice(0, dot);
      const frac = text.slice(dot + 1);
      if (!/^\d+$/.test(frac || "0") || Number.parseInt(frac || "0", 10) !== 0) {
        throw new Error("non-whole-dollar amount not allowed: " + raw);
      }
      text = whole;
    }
    if (!/^\d+$/.test(text)) throw new Error("invalid amount: " + raw);
    const value = Number.parseInt(text, 10);
    return negative ? -value : value;
  }

  function isRealDate(year, month, day) {
    if (month < 1 || month > 12 || day < 1 || day > 31) return false;
    const dt = new Date(Date.UTC(year, month - 1, day));
    return dt.getUTCFullYear() === year && dt.getUTCMonth() === month - 1 && dt.getUTCDate() === day;
  }

  function parseDate(raw) {
    const text = String(raw == null ? "" : raw).trim();
    let year;
    let month;
    let day;
    let match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
    if (match) {
      month = Number(match[1]);
      day = Number(match[2]);
      year = Number(match[3]);
    } else if ((match = /^(\d{2})\/(\d{2})\/(\d{2})$/.exec(text))) {
      month = Number(match[1]);
      day = Number(match[2]);
      const yy = Number(match[3]);
      year = yy <= 68 ? 2000 + yy : 1900 + yy;
    } else if ((match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text))) {
      year = Number(match[1]);
      month = Number(match[2]);
      day = Number(match[3]);
    } else if ((match = /^(\d{4})\/(\d{2})\/(\d{2})$/.exec(text))) {
      year = Number(match[1]);
      month = Number(match[2]);
      day = Number(match[3]);
    } else {
      throw new Error("unrecognized date: " + raw);
    }
    if (!isRealDate(year, month, day)) throw new Error("unrecognized date: " + raw);
    const mm = String(month).padStart(2, "0");
    const dd = String(day).padStart(2, "0");
    return year + "-" + mm + "-" + dd;
  }

  function formatJournalDate(isoDate) {
    return isoDate.slice(5, 7) + "/" + isoDate.slice(8, 10) + "/" + isoDate.slice(2, 4);
  }

  function normalizeCountry(raw) {
    const key = collapse(raw || "").toUpperCase();
    return COUNTRY_ALIASES[key] || key;
  }

  function firstName(cardholder) {
    const text = collapse(cardholder || "");
    if (!text) return "";
    let token = "";
    if (text.indexOf(",") !== -1) {
      const after = text.split(",", 2)[1].trim();
      token = after ? after.split(" ")[0] : "";
    } else {
      token = text.split(" ")[0];
    }
    if (!token) return "";
    return token.slice(0, 1).toUpperCase() + token.slice(1).toLowerCase();
  }

  function isPaymentThankYou(description, txnType) {
    if (String(txnType || "").trim().toLowerCase() === "payment") return true;
    return PAYMENT_THANK_YOU.test(description || "");
  }

  function leadingVendor(text) {
    const tokens = collapse(text).split(" ");
    const kept = [];
    for (let i = 0; i < tokens.length; i++) {
      const token = tokens[i];
      if (/^\d{3,}$/.test(token)) break;
      if (/^[A-Za-z]{2}$/.test(token) && kept.length) break;
      if (/^\d{5}(?:-\d{4})?$/.test(token)) break;
      const upper = token.toUpperCase();
      if ((upper === "US" || upper === "USA" || upper === "UNITED") && kept.length) break;
      kept.push(token);
      if (kept.length >= 4) break;
    }
    return collapse(kept.join(" "));
  }

  function looksLikeVendor(text) {
    const cleaned = String(text).replace(PROCESSOR_PREFIX, "");
    return /[A-Za-z]{3,}/.test(cleaned);
  }

  function stripLocationTail(text) {
    let current = text;
    for (let i = 0; i < 4; i++) {
      const nxt = current.replace(TRAILING_LOCATION, "").replace(/[ ,-]+$/g, "");
      if (nxt === current) break;
      current = nxt;
    }
    return current;
  }

  function extractVendorFirst(description, extendedDetails) {
    const desc = collapse(description || "");
    const ext = collapse(extendedDetails || "");
    let vendorSource = desc;
    if (ext) {
      const leading = leadingVendor(ext);
      const descIsProcessor = PROCESSOR_PREFIX.test(desc);
      const descIsGeneric = GENERIC_PREFIX.test(desc);
      if (leading && (descIsProcessor || descIsGeneric || !desc)) {
        vendorSource = leading;
      } else if (leading && leading.length >= (leadingVendor(desc) || "").length) {
        if (descIsProcessor || !looksLikeVendor(desc)) vendorSource = leading;
      }
    }
    let vendor = leadingVendor(vendorSource) || vendorSource;
    vendor = vendor.replace(PROCESSOR_PREFIX, "");
    vendor = stripLocationTail(vendor);
    vendor = vendor.replace(STORE_NUMBER, "");
    vendor = vendor.replace(TRAILING_STAR_CODE, "");
    vendor = collapse(vendor);
    return vendor || desc;
  }

  function merchantKey(appearsAs) {
    let text = String(appearsAs || "");
    text = text.replace(PROCESSOR_PREFIX, "");
    text = text.toLowerCase();
    text = text.split(".com").join("");
    text = text.replace(/[^a-z0-9\s*]/g, " ");
    text = text.replace(/\*+/g, " ");
    text = collapse(text);
    if (MERCHANT_ALIASES[text]) return MERCHANT_ALIASES[text];
    const parts = text.length ? text.split(" ") : [""];
    if (parts.length && PUBLIC_MERCHANT_ROOTS[parts[0]]) return parts[0];
    const key = parts.slice(0, 3).join(" ");
    return MERCHANT_ALIASES[key] || key;
  }

  function slugEntity(name) {
    const text = String(name || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    return text || "unmapped";
  }

  function rowClass(txnType, amount, description) {
    if (isPaymentThankYou(description, txnType) || String(txnType).toLowerCase() === "payment") {
      return "PAYMENT";
    }
    if (amount < 0 || String(txnType).toLowerCase() === "credit") return "CREDIT";
    return "CHARGE";
  }

  function parseCsv(text) {
    const src = String(text || "").replace(/^\uFEFF/, "");
    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;
    for (let i = 0; i < src.length; i++) {
      const ch = src[i];
      if (inQuotes) {
        if (ch === '"') {
          if (src[i + 1] === '"') {
            field += '"';
            i += 1;
          } else {
            inQuotes = false;
          }
        } else {
          field += ch;
        }
        continue;
      }
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        row.push(field);
        field = "";
      } else if (ch === "\n") {
        if (field.endsWith("\r")) field = field.slice(0, -1);
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
      } else if (ch !== "\r") {
        field += ch;
      }
    }
    if (field.length || row.length) {
      row.push(field);
      rows.push(row);
    }
    if (!rows.length) return [];
    const headers = rows[0];
    const out = [];
    for (let r = 1; r < rows.length; r++) {
      const cells = rows[r];
      if (cells.length === 1 && cells[0] === "") continue;
      const obj = {};
      for (let c = 0; c < headers.length; c++) {
        obj[headers[c]] = cells[c] == null ? "" : cells[c];
      }
      out.push(obj);
    }
    return out;
  }

  function csvEscape(value) {
    let text;
    if (value === true) text = "True";
    else if (value === false) text = "False";
    else if (value == null) text = "";
    else text = String(value);
    if (/[",\r\n]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
    return text;
  }

  function writeCsv(rows, fieldnames) {
    const lines = [fieldnames.join(",")];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const cells = [];
      for (let c = 0; c < fieldnames.length; c++) {
        const name = fieldnames[c];
        cells.push(csvEscape(Object.prototype.hasOwnProperty.call(row, name) ? row[name] : ""));
      }
      lines.push(cells.join(","));
    }
    return lines.join("\r\n") + "\r\n";
  }

  function pyJson(value) {
    return JSON.stringify(value, null, 2) + "\n";
  }

  function blankTxn(partial) {
    return {
      txn_id: "",
      cardholder_raw: "",
      cardholder_first: "",
      txn_date: "",
      post_date: "",
      description_raw: "",
      extended_details: "",
      appears_as: "",
      amount: 0,
      txn_type: "",
      country_raw: "",
      country: "",
      reference_number: "",
      row_class: "",
      entity: "",
      merchant_key: "",
      gl_code: "",
      gl_name: "",
      coding_source: "",
      confidence: "",
      review_reason: "",
      origin_kept: true,
      ...partial,
    };
  }

  function parseRawRows(rows) {
    const parsed = [];
    for (let index = 0; index < rows.length; index++) {
      const row = rows[index];
      try {
        const description = String(row.Description || "").trim();
        const txnType = String(row.Type || "").trim() || "Charge";
        let amount = parseAmount(row.Amount || "0");
        if (txnType.toLowerCase() === "credit" && amount > 0) amount = -amount;
        if (txnType.toLowerCase() === "payment" && amount > 0) amount = -amount;
        const cls = rowClass(txnType, amount, description);
        const appears = titleMerchant(extractVendorFirst(description, row["Extended Details"] || ""));
        parsed.push(
          blankTxn({
            txn_id: "T" + String(index + 1).padStart(4, "0"),
            cardholder_raw: String(row["Cardholder Name"] || "").trim(),
            cardholder_first: firstName(row["Cardholder Name"] || ""),
            txn_date: parseDate(row["Transaction Date"] || ""),
            post_date: parseDate(row["Post Date"] || row["Transaction Date"] || ""),
            description_raw: description,
            extended_details: String(row["Extended Details"] || "").trim(),
            appears_as: appears,
            amount: amount,
            txn_type: txnType,
            country_raw: String(row.Country || "").trim(),
            country: normalizeCountry(row.Country || ""),
            reference_number: String(row["Reference Number"] || "").trim(),
            row_class: cls,
            merchant_key: merchantKey(appears),
          })
        );
      } catch (err) {
        const message = err && err.message ? err.message : String(err);
        if (message.indexOf("Row ") === 0) throw err;
        throw new Error("Row " + (index + 1) + ": " + message);
      }
    }
    return parsed;
  }

  function compareRows(a, b) {
    const rank = { CHARGE: 0, CREDIT: 1, PAYMENT: 2 };
    const ra = Object.prototype.hasOwnProperty.call(rank, a.row_class) ? rank[a.row_class] : 9;
    const rb = Object.prototype.hasOwnProperty.call(rank, b.row_class) ? rank[b.row_class] : 9;
    if (ra !== rb) return ra - rb;
    if (a.txn_date !== b.txn_date) return a.txn_date < b.txn_date ? -1 : 1;
    if (a.cardholder_first !== b.cardholder_first) return a.cardholder_first < b.cardholder_first ? -1 : 1;
    if (a.txn_id !== b.txn_id) return a.txn_id < b.txn_id ? -1 : 1;
    return 0;
  }

  function cleanStatement(rawRows) {
    const parsed = parseRawRows(rawRows);
    const kept = [];
    const dropped = [];
    for (let i = 0; i < parsed.length; i++) {
      const row = parsed[i];
      if (isPaymentThankYou(row.description_raw, row.txn_type) || row.row_class === "PAYMENT") {
        dropped.push(row);
      } else {
        kept.push(row);
      }
    }
    kept.sort(compareRows);
    return { kept: kept, dropped: dropped };
  }

  function loadEntityMap(rows) {
    return rows.map(function (row) {
      return {
        first_name: String(row.first_name || "").trim(),
        full_name: String(row.full_name || "").trim(),
        entity: String(row.entity || "").trim(),
      };
    });
  }

  function applyEntityMap(rows, mapping) {
    const byFirst = {};
    for (let i = 0; i < mapping.length; i++) {
      byFirst[mapping[i].first_name.toLowerCase()] = mapping[i].entity;
    }
    const unmapped = [];
    for (let i = 0; i < rows.length; i++) {
      const entity = byFirst[rows[i].cardholder_first.toLowerCase()] || "";
      rows[i].entity = entity;
      if (!entity) unmapped.push(rows[i]);
    }
    const byEntity = {};
    for (let i = 0; i < rows.length; i++) {
      const key = rows[i].entity || "UNMAPPED";
      if (!byEntity[key]) byEntity[key] = [];
      byEntity[key].push(rows[i]);
    }
    return { tagged: rows, byEntity: byEntity, unmapped: unmapped };
  }

  function loadCoa(rows) {
    return rows.map(function (row) {
      const keywords = String(row.keywords || "")
        .split(";")
        .map(function (part) {
          return part.trim().toLowerCase();
        })
        .filter(Boolean);
      return {
        gl_code: String(row.gl_code || "").trim(),
        name: String(row.name || "").trim(),
        keywords: keywords,
      };
    });
  }

  function loadReference(rows) {
    return rows.map(function (row) {
      return {
        merchant_key: String(row.merchant_key || "").trim().toLowerCase(),
        gl_code: String(row.gl_code || "").trim(),
        times_seen: Number.parseInt(row.times_seen || "0", 10) || 0,
        appears_as: String(row.appears_as || "").trim(),
      };
    });
  }

  function containsKeyword(haystack, keyword) {
    return (" " + haystack + " ").indexOf(" " + keyword + " ") !== -1;
  }

  function coaKeywordMatches(key, appearsAs, coa) {
    const haystack = (key + " " + appearsAs).toLowerCase();
    const hits = [];
    for (let i = 0; i < coa.length; i++) {
      const acct = coa[i];
      if (!acct.keywords.length) continue;
      let matched = false;
      for (let k = 0; k < acct.keywords.length; k++) {
        if (containsKeyword(haystack, acct.keywords[k])) {
          matched = true;
          break;
        }
      }
      if (matched) hits.push(acct);
    }
    return hits;
  }

  function flagReview(row, source, reason) {
    row.gl_code = "";
    row.gl_name = "";
    row.coding_source = source;
    row.confidence = "review";
    row.review_reason = reason;
  }

  function codeTransactions(rows, reference, coa) {
    const byCode = {};
    for (let i = 0; i < coa.length; i++) byCode[coa[i].gl_code] = coa[i];
    const refByKey = {};
    for (let i = 0; i < reference.length; i++) refByKey[reference[i].merchant_key] = reference[i];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const hit = refByKey[row.merchant_key];
      if (hit) {
        if (!byCode[hit.gl_code]) {
          flagReview(row, "reference_gl_not_on_coa", "Reference GL " + hit.gl_code + " is not on the dummy COA");
          continue;
        }
        const acct = byCode[hit.gl_code];
        row.gl_code = acct.gl_code;
        row.gl_name = acct.name;
        if (hit.appears_as) row.appears_as = hit.appears_as;
        row.coding_source = "reference";
        row.confidence = "confident";
        row.review_reason = "";
        continue;
      }
      const matches = coaKeywordMatches(row.merchant_key, row.appears_as, coa);
      if (matches.length === 1) {
        row.gl_code = matches[0].gl_code;
        row.gl_name = matches[0].name;
        row.coding_source = "coa";
        row.confidence = "confident";
        row.review_reason = "";
        continue;
      }
      if (matches.length > 1) {
        flagReview(
          row,
          "ambiguous_coa",
          "Multiple COA keyword hits: " +
            matches
              .map(function (acct) {
                return acct.gl_code;
              })
              .join(", ")
        );
        continue;
      }
      flagReview(row, "no_gl", "No Reference memory or COA keyword match");
    }
    return rows;
  }

  function partitionReview(rows) {
    const coded = [];
    const review = [];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (row.confidence === "confident" && row.gl_code) coded.push(row);
      else review.push(row);
    }
    return { coded: coded, review: review };
  }

  function updateReference(reference, approved) {
    const byKey = {};
    for (let i = 0; i < reference.length; i++) byKey[reference[i].merchant_key] = reference[i];
    for (let i = 0; i < approved.length; i++) {
      const row = approved[i];
      if (row.confidence !== "confident" || !row.gl_code) continue;
      const existing = byKey[row.merchant_key];
      if (existing) {
        if (existing.gl_code !== row.gl_code) continue;
        existing.times_seen += 1;
        if (!existing.appears_as) existing.appears_as = row.appears_as;
      } else {
        byKey[row.merchant_key] = {
          merchant_key: row.merchant_key,
          gl_code: row.gl_code,
          times_seen: 1,
          appears_as: row.appears_as,
        };
      }
    }
    return Object.keys(byKey)
      .sort()
      .map(function (key) {
        return byKey[key];
      });
  }

  function expenseLine(row) {
    const desc = formatJournalDate(row.txn_date) + " - " + row.appears_as;
    if (row.amount >= 0) return { gl_code: row.gl_code, debit: row.amount, credit: 0, description: desc };
    return { gl_code: row.gl_code, debit: 0, credit: -row.amount, description: desc };
  }

  function buildJournals(byEntity, cardPayableGl) {
    const journals = {};
    const entities = Object.keys(byEntity);
    for (let i = 0; i < entities.length; i++) {
      const entity = entities[i];
      if (entity === "UNMAPPED") continue;
      const rows = byEntity[entity];
      const approved = [];
      let reviewAmt = 0;
      for (let r = 0; r < rows.length; r++) {
        const row = rows[r];
        if (row.confidence === "confident" && row.gl_code) approved.push(row);
        if (row.confidence === "review") reviewAmt += row.amount;
      }
      const lines = approved.map(expenseLine);
      let debitExp = 0;
      let creditExp = 0;
      for (let n = 0; n < lines.length; n++) {
        debitExp += lines[n].debit;
        creditExp += lines[n].credit;
      }
      const net = debitExp - creditExp;
      if (net > 0) {
        lines.push({ gl_code: cardPayableGl, debit: 0, credit: net, description: "Card Payable" });
      } else if (net < 0) {
        lines.push({ gl_code: cardPayableGl, debit: -net, credit: 0, description: "Card Payable" });
      }
      let debitTotal = 0;
      let creditTotal = 0;
      for (let n = 0; n < lines.length; n++) {
        debitTotal += lines[n].debit;
        creditTotal += lines[n].credit;
      }
      if (debitTotal !== creditTotal) {
        throw new Error(
          "Journal for " + entity + " does not balance: debit=" + debitTotal + " credit=" + creditTotal
        );
      }
      journals[entity] = {
        entity: entity,
        lines: lines,
        debit_total: debitTotal,
        credit_total: creditTotal,
        balanced: true,
        excluded_review_amount: reviewAmt,
      };
    }
    return journals;
  }

  function buildReconciliation(opts) {
    let cleanedActivity = 0;
    for (let i = 0; i < opts.cleaned.length; i++) cleanedActivity += opts.cleaned[i].amount;
    let paymentAmount = 0;
    for (let i = 0; i < opts.droppedPayments.length; i++) paymentAmount += opts.droppedPayments[i].amount;
    const entityNets = {};
    for (let i = 0; i < opts.cleaned.length; i++) {
      const key = opts.cleaned[i].entity || "UNMAPPED";
      entityNets[key] = (entityNets[key] || 0) + opts.cleaned[i].amount;
    }
    const sortedNets = {};
    const netKeys = Object.keys(entityNets).sort();
    let entitySum = 0;
    for (let i = 0; i < netKeys.length; i++) {
      sortedNets[netKeys[i]] = entityNets[netKeys[i]];
      entitySum += entityNets[netKeys[i]];
    }
    let reviewAmount = 0;
    for (let i = 0; i < opts.review.length; i++) reviewAmount += opts.review[i].amount;
    const notes = (opts.notes || []).slice();
    notes.push(VARIANCE_NOTE);
    return {
      period: opts.period,
      reported_activity: opts.reportedActivity,
      cleaned_activity: cleanedActivity,
      variance_vs_statement: cleanedActivity - opts.reportedActivity,
      payment_rows_dropped: opts.droppedPayments.length,
      payment_amount_dropped: paymentAmount,
      entity_nets: sortedNets,
      entity_sum: entitySum,
      variance_entities_vs_cleaned: entitySum - cleanedActivity,
      review_count: opts.review.length,
      review_amount: reviewAmount,
      coded_amount: cleanedActivity - reviewAmount,
      notes: notes,
    };
  }

  function renderReconciliationMd(rec, cardPayableGl) {
    const lines = [
      "# Reconciliation summary",
      "",
      "- Period: `" + rec.period + "`",
      "- Issuer-reported activity: `" + rec.reported_activity + "`",
      "- Cleaned activity (thank-you payments dropped): `" + rec.cleaned_activity + "`",
      "- Variance vs statement (cleaned \u2212 reported): `" + rec.variance_vs_statement + "`",
      "- Payment rows dropped: `" + rec.payment_rows_dropped + "` (amount `" + rec.payment_amount_dropped + "`)",
      "- Entity sum: `" + rec.entity_sum + "`",
      "- Variance entities vs cleaned: `" + rec.variance_entities_vs_cleaned + "`",
      "- Review queue: `" + rec.review_count + "` rows / `" + rec.review_amount + "` uncoded",
      "- Coded / journal-eligible: `" + rec.coded_amount + "`",
      "- Card Payable GL: `" + cardPayableGl + "`",
      "",
      "## Entity nets",
      "",
      "| Entity | Net |",
      "| --- | ---: |",
    ];
    const entities = Object.keys(rec.entity_nets);
    for (let i = 0; i < entities.length; i++) {
      lines.push("| " + entities[i] + " | " + rec.entity_nets[entities[i]] + " |");
    }
    lines.push("", "## Notes", "");
    for (let i = 0; i < rec.notes.length; i++) lines.push("- " + rec.notes[i]);
    lines.push("");
    return lines.join("\n");
  }

  function txnCsvRow(row) {
    return {
      txn_id: row.txn_id,
      cardholder_raw: row.cardholder_raw,
      cardholder_first: row.cardholder_first,
      txn_date: row.txn_date,
      post_date: row.post_date,
      description_raw: row.description_raw,
      extended_details: row.extended_details,
      appears_as: row.appears_as,
      amount: String(row.amount),
      txn_type: row.txn_type,
      country_raw: row.country_raw,
      country: row.country,
      reference_number: row.reference_number,
      row_class: row.row_class,
      entity: row.entity,
      merchant_key: row.merchant_key,
      gl_code: row.gl_code,
      gl_name: row.gl_name,
      coding_source: row.coding_source,
      confidence: row.confidence,
      review_reason: row.review_reason,
      origin_kept: row.origin_kept,
    };
  }

  function journalCsvRow(line) {
    return {
      "GL Code": line.gl_code,
      Debit: line.debit === 0 ? "" : String(line.debit),
      Credit: line.credit === 0 ? "" : String(line.credit),
      Description: line.description,
    };
  }

  function referenceCsvRow(item) {
    return {
      merchant_key: item.merchant_key,
      gl_code: item.gl_code,
      times_seen: String(item.times_seen),
      appears_as: item.appears_as,
    };
  }

  function runSummary(result) {
    const journals = {};
    const names = Object.keys(result.journals);
    for (let i = 0; i < names.length; i++) {
      const journal = result.journals[names[i]];
      journals[names[i]] = {
        lines: journal.lines.length,
        debit_total: journal.debit_total,
        credit_total: journal.credit_total,
        balanced: journal.balanced,
        excluded_review_amount: journal.excluded_review_amount,
      };
    }
    return {
      cleaned_rows: result.cleaned.length,
      origin_rows: result.origin.length,
      dropped_payment_rows: result.droppedPayments.length,
      entities: Object.keys(result.byEntity).sort(),
      coded_rows: result.coded.length,
      review_rows: result.review.length,
      journals: journals,
      card_payable_gl: result.cardPayableGl,
      unmapped_rows: result.unmapped.length,
    };
  }

  function cloneRow(row) {
    return blankTxn(row);
  }

  function runPipeline(inputs) {
    const raw = parseCsv(inputs.rawStatementCsv);
    const meta = JSON.parse(inputs.statementMetaJson);
    const coa = loadCoa(parseCsv(inputs.chartOfAccountsCsv));
    const reference = loadReference(parseCsv(inputs.referenceCsv));
    const mapping = loadEntityMap(parseCsv(inputs.entityMapCsv));

    let payable = "";
    for (let i = 0; i < coa.length; i++) {
      if (coa[i].name.toLowerCase() === "card payable") {
        payable = coa[i].gl_code;
        break;
      }
    }
    if (!payable) throw new Error("The chart of accounts needs an account named Card Payable.");

    const cleanedPair = cleanStatement(raw);
    const cleaned = cleanedPair.kept;
    const dropped = cleanedPair.dropped;
    const origin = cleaned.map(cloneRow);
    const split = applyEntityMap(cleaned, mapping);
    codeTransactions(split.tagged, reference, coa);
    const parts = partitionReview(split.tagged);
    const referenceUpdated = updateReference(reference, parts.coded);
    const journals = buildJournals(split.byEntity, payable);
    const extraNotes = [];
    if (split.unmapped.length) {
      extraNotes.push(
        split.unmapped.length +
          " cleaned row(s) have no entity map; they stay on Origin and land under UNMAPPED. Totals are not force-matched."
      );
    }
    const rec = buildReconciliation({
      period: String(meta.period || ""),
      reportedActivity: Number.parseInt(meta.reported_activity || 0, 10) || 0,
      cleaned: split.tagged,
      droppedPayments: dropped,
      review: parts.review,
      notes: extraNotes,
    });
    return {
      cleaned: split.tagged,
      origin: origin,
      byEntity: split.byEntity,
      coded: parts.coded,
      review: parts.review,
      journals: journals,
      reconciliation: rec,
      referenceUpdated: referenceUpdated,
      droppedPayments: dropped,
      cardPayableGl: payable,
      unmapped: split.unmapped,
      coa: coa,
    };
  }

  function renderOutputs(result) {
    const files = {};
    function txnFile(rows) {
      return writeCsv(
        rows.map(function (row) {
          return txnCsvRow(row);
        }),
        TXN_FIELDS
      );
    }
    files["cleaned.csv"] = txnFile(result.cleaned);
    files["origin.csv"] = txnFile(result.origin);
    files["coded.csv"] = txnFile(result.coded);
    files["review_queue.csv"] = txnFile(result.review);
    files["dropped_payments.csv"] = txnFile(result.droppedPayments);
    files["reference_updated.csv"] = writeCsv(
      result.referenceUpdated.map(referenceCsvRow),
      ["merchant_key", "gl_code", "times_seen", "appears_as"]
    );
    const splitNames = Object.keys(result.byEntity);
    for (let i = 0; i < splitNames.length; i++) {
      const entity = splitNames[i];
      files["split/" + slugEntity(entity) + ".csv"] = txnFile(result.byEntity[entity]);
    }
    const journalNames = Object.keys(result.journals);
    for (let i = 0; i < journalNames.length; i++) {
      const entity = journalNames[i];
      files["journals/" + slugEntity(entity) + ".csv"] = writeCsv(
        result.journals[entity].lines.map(journalCsvRow),
        JOURNAL_FIELDS
      );
    }
    files["reconciliation.json"] = pyJson(result.reconciliation);
    files["reconciliation.md"] = renderReconciliationMd(result.reconciliation, result.cardPayableGl);
    files["run_summary.json"] = pyJson(runSummary(result));
    return files;
  }

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) {
      c ^= bytes[i];
      for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
    }
    return (c ^ 0xffffffff) >>> 0;
  }

  function buildZip(files) {
    const encoder = new TextEncoder();
    const names = Object.keys(files);
    const locals = [];
    const centrals = [];
    let offset = 0;
    const dosDate = ((2026 - 1980) << 9) | (3 << 5) | 1;
    for (let i = 0; i < names.length; i++) {
      const nameBytes = encoder.encode(names[i]);
      const data = encoder.encode(files[names[i]]);
      const crc = crc32(data);
      const local = new Uint8Array(30 + nameBytes.length + data.length);
      const view = new DataView(local.buffer);
      view.setUint32(0, 0x04034b50, true);
      view.setUint16(4, 20, true);
      view.setUint16(8, 0, true);
      view.setUint16(10, 0, true);
      view.setUint16(12, dosDate, true);
      view.setUint32(14, crc, true);
      view.setUint32(18, data.length, true);
      view.setUint32(22, data.length, true);
      view.setUint16(26, nameBytes.length, true);
      local.set(nameBytes, 30);
      local.set(data, 30 + nameBytes.length);
      locals.push(local);

      const central = new Uint8Array(46 + nameBytes.length);
      const cv = new DataView(central.buffer);
      cv.setUint32(0, 0x02014b50, true);
      cv.setUint16(4, 20, true);
      cv.setUint16(6, 20, true);
      cv.setUint16(10, 0, true);
      cv.setUint16(12, 0, true);
      cv.setUint16(14, dosDate, true);
      cv.setUint32(16, crc, true);
      cv.setUint32(20, data.length, true);
      cv.setUint32(24, data.length, true);
      cv.setUint16(28, nameBytes.length, true);
      cv.setUint32(42, offset, true);
      central.set(nameBytes, 46);
      centrals.push(central);
      offset += local.length;
    }
    let centralSize = 0;
    for (let i = 0; i < centrals.length; i++) centralSize += centrals[i].length;
    const eocd = new Uint8Array(22);
    const ev = new DataView(eocd.buffer);
    ev.setUint32(0, 0x06054b50, true);
    ev.setUint16(8, names.length, true);
    ev.setUint16(10, names.length, true);
    ev.setUint32(12, centralSize, true);
    ev.setUint32(16, offset, true);
    const out = new Uint8Array(offset + centralSize + 22);
    let pos = 0;
    for (let i = 0; i < locals.length; i++) {
      out.set(locals[i], pos);
      pos += locals[i].length;
    }
    for (let i = 0; i < centrals.length; i++) {
      out.set(centrals[i], pos);
      pos += centrals[i].length;
    }
    out.set(eocd, pos);
    return out;
  }

  return {
    parseCsv: parseCsv,
    runPipeline: runPipeline,
    renderOutputs: renderOutputs,
    buildZip: buildZip,
    slugEntity: slugEntity,
  };
});
