const sites = require('../../services/siteServices');

async function importIdentificadores(req, res) {
    
    let response = { result: "NOK" };

    try {

        const data = req.body;

        if (!Array.isArray(data)) {
            console.log("NO ARRAY")
            return res.status(400).json({
                result: "NOK",
                msg: "El body debe ser un array de objetos"
            });
        }

        if (data.length === 0) {
            console.log("NO DATA")
            return res.status(400).json({
                result: "NOK",
                msg: "No se recibieron registros para importar"
            });
        }


        const result = await sites.importIdentificadoresService(data);

        if(!result) return res.status(400).json({ok: false, error: 'Error to insert data'})
        res.status(200).json({ message: "ok", content: result })
        // res.status(200).json({ message: "ok", content: data })

    } catch (error) {
        console.error(`Error while logged users: ${error}`)
        res.status(500).json({ message: "nok", content: 'Error to insert data' })
    }
}

async function getSites(req, res) {
    try {
        const data = await sites.getSitesService()
        res.status(200).json({ message: "ok", content: data })
    } catch (error) {
        console.error(`Error while logged users: ${error}`)
        res.status(500).json({ message: "nok", content: 'Error to insert data' })
    }
}

const updateIdentificadoresByType = async (req, res) => {
    try {

        // console.log("REQ BODY", req.body)

        const { tipoProyecto, rows } = req.body;

        // console.log("ROWS", rows)

        if (!tipoProyecto) {
            return res.status(400).json({
                result: "NOK",
                msg: "tipoProyecto es requerido",
            });
        }

        if (!Array.isArray(rows)) {
            return res.status(400).json({
                result: "NOK",
                msg: "rows debe ser un array",
            });
        }

        const result = await sites.updateIdentificadoresByType({
            tipoProyecto,
            rows,
        });

        return res.json({
            result: "OK",
            content: result,
        });
    } catch (error) {
        console.error("Error updateIdentificadoresByType:", error);
        return res.status(500).json({
            result: "ERROR",
            msg: error.message,
        });
    }
};

module.exports = {
    importIdentificadores,
    getSites,
    updateIdentificadoresByType
}