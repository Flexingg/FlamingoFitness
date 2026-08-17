/**
 * Flamingo Fitness — Item Catalog Exporter
 * ==========================================
 * Bound to a Google Sheet that author the item catalog for the Gacha / gear
 * system. Reads author-friendly rows and emits the JSON blob that gets pasted
 * into config/seeds/gear_items.json (and optionally config/seeds/scrap_shop.json).
 *
 * Design guide: docs/16_Item_Design_Guide.md
 *
 * Sheets this script reads (each tab):
 *   - "GearItems"   -> rows for GearItemDef  (config/seeds/gear_items.json)
 *   - "ScrapShop"   -> rows for ScrapShopItem (config/seeds/scrap_shop.json)
 *
 * The script AUTO-CREATES missing tabs and writes the header row into
 * blank sheets on every run (ensureTables), so it also works when the
 * spreadsheet is empty.
 *
 * How to use:
 *   1. Open your spreadsheet in Google Sheets.
 *   2. Extensions -> Apps Script, paste this file (code.gs) as the project.
 *   3. Run exportItemsJson() / exportScrapShopJson() from the toolbar, or
 *      exportAllJson() to generate both at once.
 *   4. Copy the JSON the script logs (View -> Logs) into the matching
 *      config/seeds/*.json file.
 *
 * Column order does not matter: the first row is a header of FIELD NAMES (the
 * JSON keys from the docs), so re-ordering or adding columns is safe as long as
 * you match the header names exactly.
 */

var FIELD_ROWS = {
  GearItems: [
    'slug', 'name', 'slot', 'rarity', 'icon', 'effect_type', 'effect_domain',
    'effect_value', 'effect_params', 'requires_sleep_efficiency', 'pack',
    'weight', 'is_consumable', 'max_stack', 'description', 'is_active',
    'sort_order'
  ],
  ScrapShop: [
    'slug', 'name', 'icon', 'description', 'cost_scraps', 'available_days',
    'reward_type', 'reward_value', 'pack', 'is_active', 'sort_order'
  ]
};

/** Build {fieldName: columnIndex} from the first row of a sheet. */
function readHeader(sheet) {
  var first = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var map = {};
  for (var col = 0; col < first.length; col++) {
    var h = String(first[col] == null ? '' : first[col]).trim().toLowerCase();
    if (h) map[h] = col;
  }
  return map;
}

/** Coerce a cell value to a string (null stays null). */
function str(v) { return (v == null || String(v).trim() === '') ? null : String(v).trim(); }

/** Number, or a sentinel-default when blank. */
function num(v, dflt) {
  if (v == null || String(v).trim() === '') return dflt;
  return Number(String(v).trim().replace(',', ''));
}

/** Integer, or default when blank. */
function int(v, dflt) { var n = num(v, dflt); return Math.round(n); }

/** Boolean from yes/no/true/false/1/0. Default when blank. */
function bool(v, dflt) {
  if (v == null || String(v).trim() === '') return !!dflt;
  var s = String(v).trim().toLowerCase();
  if (['true', 'yes', 'y', '1'].indexOf(s) !== -1) return true;
  if (['false', 'no', 'n', '0'].indexOf(s) !== -1) return false;
  return !!dflt;
}

/** JSON string in a cell, or the default (dict/list). */
function json(v, dflt) {
  if (v == null || String(v).trim() === '') return dflt;
  var s = String(v).trim();
  try { return JSON.parse(s); } catch (e) { return dflt; }
}

/** list-of-weekday-int cell for ScrapShop: "0,2,4" -> [0,2,4]. */
function daylist(v) {
  if (v == null || String(v).trim() === '') return null; // null = every day
  return String(v).split(/[,;\s]+/).filter(function (x) {
    return x.trim() !== '';
  }).map(function (x) { return parseInt(x, 10); });
}

/** Reverse the {field: col} map into an array of {field, col}. */
function ordered(fields, header) {
  return fields.filter(function (f) { return header[f] !== undefined; })
    .map(function (f) { return { field: f, col: header[f] }; });
}

/** Create any missing tabs and write the header row into blank sheets. */
function ensureTables() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  Object.keys(FIELD_ROWS).forEach(function (name) {
    var fieldNames = FIELD_ROWS[name];
    var sheet = ss.getSheetByName(name);
    if (!sheet) {
      sheet = ss.insertSheet(name);
    }
    // If the first row is blank, write the header names once.
    var first = sheet.getRange(1, 1, 1, sheet.getLastColumn() || 1).getValues()[0];
    var hasHeader = first.some(function (c) {
      return c !== null && String(c).trim() !== '';
    });
    if (!hasHeader) {
      sheet.getRange(1, 1, 1, fieldNames.length).setValues([fieldNames.slice()]);
    }
  });
}

/** Read all data rows for a configured sheet name into JSON-ready objects. */
function rowsFor(sheetName) {
  ensureTables();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(sheetName);
  var fieldNames = FIELD_ROWS[sheetName];
  var header = readHeader(sheet);

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  var data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  var cols = ordered(fieldNames, header);
  var out = [];

  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    var rec = {};
    for (var ci = 0; ci < cols.length; ci++) {
      var f = cols[ci].field;
      var v = row[cols[ci].col];
      rec[f] = coerce(f, v);
    }
    // Skip fully blank rows.
    var hasContent = Object.keys(rec).some(function (k) {
      return rec[k] !== null && rec[k] !== undefined && rec[k] !== '';
    });
    if (!hasContent) continue;
    // A SlugColumn is required; drop blank stubs.
    if (!rec.slug) continue;
    out.push(rec);
  }
  return out;
}

/** Type-coerce one field per its schema (see FIELD_ROWS). */
function coerce(field, v) {
  switch (field) {
    case 'effect_value':
    case 'requires_sleep_efficiency':
    case 'reward_value':
    case 'cost_scraps':
      return num(v, 0);
    case 'weight':
    case 'sort_order':
    case 'max_stack':
      return int(v, 0);
    case 'is_consumable':
    case 'is_active':
      return bool(v, false);
    case 'effect_params':
      return json(v, {});
    case 'available_days':
      return daylist(v);
    default:
      return str(v);
  }
}

function prettyJson(rows) {
  return JSON.stringify(rows, null, 2);
}

/** Export the GearItems tab -> config/seeds/gear_items.json JSON. */
function exportItemsJson() {
  var rows = rowsFor('GearItems');
  var out = prettyJson(rows);
  Logger.log(out);
  return out;
}

/** Export the ScrapShop tab -> config/seeds/scrap_shop.json JSON. */
function exportScrapShopJson() {
  var rows = rowsFor('ScrapShop');
  var out = prettyJson(rows);
  Logger.log(out);
  return out;
}

/** Export every configured tab. Returns {tabName: jsonString}. */
function exportAllJson() {
  var result = {};
  Object.keys(FIELD_ROWS).forEach(function (name) {
    result[name] = prettyJson(rowsFor(name));
    Logger.log('===== ' + name + ' =====');
    Logger.log(result[name]);
  });
  return result;
}
