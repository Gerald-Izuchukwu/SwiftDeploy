const dotenv = require('dotenv');
dotenv.config();
const express = require('express');
const app = express()
const {Registry, Gauge, Histogram, Counter} = require('prom-client')
const PORT = process.env.PORT || 3000;
app.use(express.json())
const MODE = process.env.MODE || 'stable'

const header = {
    "X-Mode": MODE,
}
// Chaos state - shared across routes
let chaosState = { mode: 'none', rate: 0, duration: 0 };

const register = new Registry();

const httpRequestsTotal = new Counter({
  name: 'http_requests_total',
  help: 'Total HTTP requests served',
  labelNames: ['method', 'path', 'status_code'],
  registers: [register],
});

const httpRequestDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'Request latency histogram',
  buckets: [0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
  registers: [register],
});

const appUptime = new Gauge({
  name: 'app_uptime_seconds',
  help: 'Seconds since process start',
  registers: [register],
});

const appMode = new Gauge({
  name: 'app_mode',
  help: 'App mode: 0=stable, 1=canary',
  registers: [register],
});
appMode.set(MODE === 'canary' ? 1 : 0);

const chaosActive = new Gauge({
  name: 'chaos_active',
  help: 'Chaos state: 0=none, 1=slow, 2=error',
  registers: [register], 
});

// middleware to record all requests, this middleware runs before every route
app.use((req, res, next)=>{
    const startTime = process.hrtime.bigint() 
    res.on('finish',()=>{
        const duration = process.hrtime.bigint() - startTime 
        const durationSeconds = Number(duration)/ 1e9

        httpRequestDuration.observe(durationSeconds) 
        httpRequestsTotal.labels(req.method, req.path, String(res.statusCode)).inc() 
        appUptime.set(process.uptime())
    })
    next()
})

app.get('/', async (req, res)=>{
    if (chaosState.mode === "slow"){
         await new Promise(resolve => setTimeout(resolve, chaosState.duration * 1000));
    }else if (chaosState.mode === 'error' && Math.random() < chaosState.rate) {
        return res.status(500).json({ error: 'chaos induced error' });
    }
    res.set(header)

    res.status(200).json({
        message: "Welcome to SwiftDeploy CLI",
        current_mode : MODE,
        version: process.env.VERSION,
        timestamp: new Date().toLocaleString()

    })
    console.log(res.getHeaders())
})

app.get('/healthz', (req, res)=>{
    res.set(header)
    res.status(200).json({
        status: "ok",
        uptime: process.uptime().toLocaleString(),
        timestamp: new Date().toLocaleString()
    })  
})

app.get('/metrics', async(req, res)=>{
    appUptime.set((Date.now() - START_TIME) / 1000);
    res.setHeader('Content-Type', register.contentType);
    res.send(await register.metrics());
})

app.post('/chaos', (req,res)=>{
    res.set(header)

    if (MODE !== 'canary') {
        return res.status(403).json({ error: 'chaos only available in canary mode' });
    }
    const {mode, duration, rate} = req.body

    if(mode === "slow"){
        chaosState = {mode: "slow", duration: duration || 5, rate: 0}
        chaosActive.set(1) //update guage
        return res.status(200).json({
            message: `Response delayed by ${duration} ms`,
            chaos: "slow",
            duration : chaosState.duration
        })
    }

    else if(mode === "error"){
        chaosState = { mode: "error", duration: 0, rate: rate || 0.5 }
        chaosActive.set(2)
        return res.status(200).json({
            message: "Simulated error response",
            chaos: "error",
            rate: rate
        })
    }

    else if (mode === "recover"){
        chaosState = { mode: 'none', rate: 0, duration: 0 };
        chaosActive.set(0)
        return res.status(200).json({
            message: "System recovered to normal state"
        })
    }
    else{
        return res.status(400).json({ error: 'invalid chaos mode' });
    }

})


app.listen(PORT, "0.0.0.0",  ()=>{
    console.log(`Server is running on port ${PORT}`)
})





































// function times(){
//     const time1 = new Date().toISOString();
//     const time2 = new Date().toLocaleString();
//     const time3 = new Date().getTime();
//     const uptime = process.uptime().toLocaleString()
//     console.log({time1, time2, time3, uptime})
// }

// times();


// let chaosState = { mode: 'none', rate: 0, duration: 0 };

// app.use(async (req, res, next) => {
//   if (chaosState.mode === 'global-slow') {
//     await delay(chaosState.duration);
//   }
//   next();
// });