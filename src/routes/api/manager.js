module.exports = function(app) {
    /****************************** GCIR - PORTAL CALIDAD ********************************************/
    //TEMP: API budget
    app.use('/api/budget', require('../../controllers/budget/budget'));
    app.use('/api', require('../../controllers/login/loginController'));
};