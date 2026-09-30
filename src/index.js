const express = require('express');
const morgan = require('morgan');
const cors = require('cors');
const error404Handler = require('./middleware/notFound');
const errorHandler = require('./middleware/errorHandler');
const loginRouter = require('./routes/api/loginRouter');
const pyRouter = require('./routes/api/pyRouter');
const dotenv = require('dotenv');
const projectsRouter = require('./routes/api/projectsRouter');
const authRouter = require('./routes/api/authRouter');
// const m365Router = require('./routes/api/m365');
const siteRouter = require('./routes/api/siteRouter');
const usersRouter = require('./routes/api/usersRouter');
const groupUsersRouter = require('./routes/api/groupUsersRouter');

// Config
const app = express();
dotenv.config();

app.use(morgan('dev'));
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// PORT
const PORT = process.env.PORT || 3000;

// CORS
app.use(cors({
	origin: true,
	methods: ["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
	allowedHeaders: ["Content-Type","Authorization"]
}));

app.options(/.*/, cors());

// HEADERS
app.use((req, res, next) => {
	res.setHeader(
		"Content-Security-Policy", 
		"default-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com 'unsafe-inline'; script-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com 'unsafe-inline' 'unsafe-eval'"
	);
	res.setHeader("X-Content-Type-Options", "nosniff");
	res.setHeader("X-Permitted-Cross-Domain-Policies", "none");
	res.setHeader("Referrer-Policy", "no-referrer");
	next();
});


// app.use((req, res, next) => {

// 	const origin = req.headers.origin || '*';

// 	res.setHeader('Access-Control-Allow-Origin', origin);
// 	res.setHeader('Access-Control-Allow-Methods', 'OPTIONS, GET, POST, PUT, PATCH, DELETE');
// 	res.setHeader('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Authorization');

// 	if(req.method === 'OPTIONS') return res.sendStatus(204);

// 	res.setHeader(
//         'Content-Security-Policy',
//         "default-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com 'unsafe-inline'; script-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com 'unsafe-inline' 'unsafe-eval'"
//     );
// 	res.setHeader('X-Content-Type-Options', 'nosniff');
// 	res.setHeader('X-Permitted-Cross-Domain-Policies', 'none');
// 	res.setHeader('Referrer-Policy','no-referrer')
// 	next()

// });


// TEST
app.get('/', (req, res) => {
  	res.send('Hello World!');
});


// API routes(call routes)
app.use('/api/', loginRouter)
app.use('/api/', authRouter)
app.use('/api/', pyRouter)
app.use('/api/', projectsRouter)
app.use('/api/', siteRouter)
app.use('/api/', usersRouter)
app.use('/api', groupUsersRouter)

// Error
app.use(error404Handler)
app.use(errorHandler)


// require('./routes/api/manager')(app);

app.listen(PORT, () => {
  	console.log(`Server is running on port ${PORT}`);
});