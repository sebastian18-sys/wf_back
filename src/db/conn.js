// // import { promisify } from "util";
// const { promisify } = require('util');
// const mysql = require("mysql2/promise");

// async function createDb() {

//   const env = process.env.NODE_ENV || "development";

//   if (env !== "production") {
    
//     const pool = mysql.createPool({
// 		host: process.env.MYSQL_HOST,
// 		port: Number(process.env.MYSQL_PORT || 3306),
// 		user: process.env.MYSQL_USER,
// 		password: process.env.MYSQL_PASSWORD,
// 		database: process.env.MYSQL_DATABASE,
// 		waitForConnections: true,
// 		connectionLimit: 10,
// 		queueLimit: 0,
//     });

// 	 return {
// 		type: "mysql",
// 		query: async (sql, params = []) => {
// 			// Devuelve rows (objetos)
// 			const [rows] = await pool.execute(sql, params)
// 			return rows
// 		},
// 		close: () => pool.end(),
// 		raw: pool
//     }
//   }

//   // production => oracle
//   const oracledb = require("oracledb");
//   oracledb.outFormat = oracledb.OUT_FORMAT_OBJECT;

//   const pool = await oracledb.createPool({
//     user: process.env.ORACLE_USER,
//     password: process.env.ORACLE_PASSWORD,
//     connectString: process.env.ORACLE_CONNECT_STRING,
//     poolMin: 1,
//     poolMax: 10,
//     poolIncrement: 1,
//   });

//   return {
//     type: "oracle",
//     query: async (sql, params = {}) => {
// 		const conn = await pool.getConnection();
// 		try {
// 			const r = await conn.execute(sql, params, { autoCommit: false });
// 			return r.rows ?? r;
// 		} finally {
// 			await conn.close();
// 		}
//     },
//     close: async () => pool.close(10),
//   };
// }

// module.exports = { createDb };

const mysql = require("mysql2/promise")
const oracledb = require("oracledb")

let dbPromise = null

async function createDb() {
	const env = process.env.NODE_ENV || "development"

	// DEV => MySQL2
	if (env !== "production") {
		const pool = mysql.createPool({
			host: process.env.MYSQL_HOST,
			port: process.env.MYSQL_PORT,
			user: process.env.MYSQL_USER,
			password: process.env.MYSQL_PASSWORD,
			database: process.env.MYSQL_DATABASE,
			waitForConnections: true,
			connectionLimit: 10,
			queueLimit: 0,
		})

		return {
			type: "mysql",
			query: async (sql, params = []) => {
				const [rows] = await pool.execute(sql, params)
				return rows
			},

			getConnection: async () => {
				return await pool.getConnection();
			},

			close: () => pool.end()
		}
	}

	// PROD => Oracle
	oracledb.outFormat = oracledb.OUT_FORMAT_OBJECT

	const pool = await oracledb.createPool({
		user: process.env.ORACLE_USER,
		password: process.env.ORACLE_PASSWORD,
		connectString: process.env.ORACLE_CONNECT_STRING,
		poolMin: 1,
		poolMax: 10,
		poolIncrement: 1,
	})

	return {
		type: "oracle",
		query: async (sql, bindParams = {}, options = {}) => {
		const conn = await pool.getConnection()
		try {
			const r = await conn.execute(sql, bindParams, { autoCommit: false, ...options })
			return r.rows ?? r
		} finally {
			await conn.close()
		}
		},
		close: () => pool.close(10),
	}
}

function getDb() {
  if (!dbPromise) dbPromise = createDb() // se crea 1 sola vez
  return dbPromise
}

async function query(sql, paramsOrBinds, options) {
  const db = await getDb()
  return db.query(sql, paramsOrBinds, options)
}

async function getConnection() {
  const db = await getDb()
  return db.getConnection()
}

async function close() {
  if (!dbPromise) return
  const db = await dbPromise
  await db.close()
}

module.exports = { getDb, query , getConnection, close }