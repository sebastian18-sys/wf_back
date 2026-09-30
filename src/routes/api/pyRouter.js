const pyRouter = require('express').Router()
const pyController = require('../../controllers/python/pyController')
const userExtractor = require('../../middleware/userExtractor')
const { upload } = require('../../utils/multer')

// LOGIN ROUTER
pyRouter.get('/capex/scenarios-opex', pyController.scenariosOpex)
pyRouter.post('/capex/scenarios-opex-data', pyController.scenariosOpexData)
pyRouter.post('/capex/upload-data-capex', userExtractor, upload.any(), pyController.uploadDataCapex)
pyRouter.get('/capex/testdb', pyController.testdb)

module.exports = pyRouter