function excelSerialToMysqlDate(serial) {
    const n = Number(serial);
    if (!Number.isFinite(n)) return null;

    // Excel base date
    const base = new Date(Date.UTC(1899, 11, 30));
    const date = new Date(base.getTime() + n * 24 * 60 * 60 * 1000);

    const yyyy = date.getUTCFullYear();
    const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(date.getUTCDate()).padStart(2, "0");

    return `${yyyy}-${mm}-${dd}`;
}

function normalizeDate(value) {
    if (value == null || String(value).trim() === "") return null;

    const v = String(value).trim();

    // Caso Excel serial: 46032
    if (/^\d+$/.test(v)) {
        return excelSerialToMysqlDate(v);
    }

    // Caso dd/mm/yyyy
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(v)) {
        const [dd, mm, yyyy] = v.split("/");
        return `${yyyy}-${mm}-${dd}`;
    }

    return null; // o lanzar error si quieres validar estricto
}

module.exports = {
    normalizeDate
};