const db = require("../db/conn");
const { normalizeDate } = require("../utils/dateFormat");

async function importIdentificadoresService(items) {

    const conn = await db.getConnection();

    try {

        await conn.beginTransaction();

        // Borra lo anterior
        await conn.query(`DELETE FROM identificadores`);

        const values = items.map((item) => [
            String(item.identificador ?? "").trim(),
            String(item.tipo ?? "").trim(),
            String(item.site ?? "").trim(),
            String(item.id_proyecto ?? "").trim(),
            String(item.nombre_proyecto ?? "").trim(),
            String(item.sub_proyecto ?? null).trim(),
            String(item.estado ?? "").trim(),
            normalizeDate(item.date_fcst ?? null),
            normalizeDate(item.date_real ?? null),
        ]);

        if (values.length > 0) {
            await conn.query(
                `
                    INSERT INTO identificadores
                        (name, project_type, site, project_code, project_name, project_sub, state, date_fcst, date_real)
                    VALUES ?
                `,
                [values]
            );
        }

        await conn.commit();

        return {
            inserted: values.length,
        };
    } catch (error) {
        await conn.rollback();
        console.error(`exec error: ${error}`);
        return { error: error.message }
    } finally {
        conn.release();
    }
}

async function getSitesService() {
    try {
        const sitesData = await db.query(`
            SELECT 
                *,
                DATE_FORMAT(date_fcst, "%d/%m/%Y") AS date_fcst,
                DATE_FORMAT(date_real, "%d/%m/%Y") AS date_real
            FROM identificadores
        `)
        return sitesData
    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}

async function updateIdentificadoresByType({ tipoProyecto, rows }) {

    const conn = await db.getConnection();

    try {
        await conn.beginTransaction();

        await conn.query(
            `DELETE FROM identificadores WHERE project_type = ?`,
            [tipoProyecto]
        );

        if (rows.length > 0) {
            const values = rows.map((row) => [
                String(row.name ?? "").trim(),
                String(row.project_type ?? "").trim(),
                String(row.site ?? "").trim(),
                String(row.project_code ?? "").trim(),
                String(row.project_name ?? "").trim(),
                String(row.project_sub ?? null).trim(),
                String(row.state ?? "").trim(),
                normalizeDate(row.date_fcst ?? null),
                normalizeDate(row.date_real ?? null),
            ]);

            await conn.query(
                `
                INSERT INTO identificadores
                (name, project_type, site, project_code, project_name, project_sub, state, date_fcst, date_real)
                VALUES ?
                `,
                [values]
            );
        }

        await conn.commit();

        return {
            tipoProyecto,
            total: rows.length,
        };
    } catch (error) {
        await conn.rollback();
        throw error;
    } finally {
        conn.release();
    }
}

module.exports = {
    importIdentificadoresService,
    getSitesService,
    updateIdentificadoresByType
};