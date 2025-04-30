import asyncio
import logging
import uuid
import json
import datetime
import time
import traceback
from fastapi import FastAPI, WebSocket, HTTPException
from typing import List, Dict, Any, Optional
import asyncssh
from pydantic import BaseModel
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi.middleware.cors import CORSMiddleware

# 数据库配置
DATABASE_URL = "sqlite:///./test.db"  # SQLite数据库
Base = declarative_base()


class ServerCommandResult(Base):
    __tablename__ = 'server_command_results'
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, index=True)
    user = Column(String)
    password = Column(String)
    port = Column(Integer, default=22)
    command = Column(String)
    output = Column(Text)
    exit_status = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


# 服务器配置存储模型
class ServerConfig(Base):
    __tablename__ = 'server_configs'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # 配置名称
    config_data = Column(Text)  # 存储JSON格式的配置数据
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# 创建数据库引擎和会话
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 日志配置 - 增强为结构化日志
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # 添加额外信息
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
            
        # 添加其他自定义字段
        for key, value in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "id", "levelname", "levelno", "lineno", "module",
                "msecs", "message", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread", "threadName"
            } and not key.startswith("_"):
                log_data[key] = value
        
        # 处理异常信息
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            log_data["exception"] = {
                "type": exc_type.__name__,
                "message": str(exc_value),
                "traceback": traceback.format_exception(exc_type, exc_value, exc_traceback)
            }
        
        return json.dumps(log_data)

# 配置日志
level = logging.DEBUG if os.getenv("DEBUG_MODE", "False").lower() in ("true", "1", "t") else logging.INFO
logger = logging.getLogger(__name__)
logger.setLevel(level)

# 如果需要结构化JSON日志，取消下面注释
"""
# 移除所有现有处理器
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 添加控制台处理器
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
"""

# 创建FastAPI应用
app = FastAPI()

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SSH连接池
ssh_connections = {}
# 修改 get_ssh_connection 函数中的连接检查逻辑
async def get_ssh_connection(host, username, password, port=22):
    """从连接池获取SSH连接或创建新连接"""
    key = f"{host}:{port}:{username}"
    
    # 检查是否有可用的缓存连接
    if key in ssh_connections:
        try:
            # 尝试执行一个简单的命令来验证连接是否活跃
            # 如果连接断开，这里会抛出异常
            conn = ssh_connections[key]["conn"]
            # 可以在这里添加一个简单的检查，例如尝试运行一个无害命令
            # 但这可能会增加额外开销，所以也可以直接假设连接是活跃的
            # 如果连接已断开，在使用时会抛出异常并被捕获
            
            ssh_connections[key]["last_used"] = time.time()
            logger.debug(f"Reusing SSH connection to {host}:{port}", extra={"connection_key": key})
            return conn
        except Exception as e:
            # 连接可能已关闭或失效，记录日志并从池中移除
            logger.warning(f"Cached SSH connection to {host}:{port} is invalid, creating new one: {e}")
            if key in ssh_connections:
                del ssh_connections[key]
    
    # 创建新连接
    try:
        conn = await asyncssh.connect(
            host, 
            username=username, 
            password=password, 
            port=port, 
            known_hosts=None,
            connect_timeout=60  # 10秒连接超时
        )
        ssh_connections[key] = {
            "conn": conn,
            "last_used": time.time()
        }
        logger.info(f"Created new SSH connection to {host}:{port}", extra={"connection_key": key})
        return conn
    except Exception as e:
        logger.error(f"Error creating SSH connection to {host}:{port}: {e}", exc_info=True, 
                   extra={"host": host, "port": port, "username": username})
        raise
# 修改 cleanup_connections 函数
async def cleanup_connections():
    """清理10分钟未使用的SSH连接"""
    while True:
        await asyncio.sleep(300)  # 5分钟检查一次
        current_time = time.time()
        cleaned = 0
        
        for key, data in list(ssh_connections.items()):
            if current_time - data["last_used"] > 600:  # 10分钟未使用
                try:
                    # 尝试关闭连接
                    try:
                        data["conn"].close()
                    except Exception as e:
                        logger.error(f"Error closing SSH connection: {e}", extra={"connection_key": key})
                    
                    del ssh_connections[key]
                    cleaned += 1
                except Exception as e:
                    logger.error(f"Error during connection cleanup: {e}", extra={"connection_key": key})
        
        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} idle SSH connections")

# WebSocket连接注册表
websockets = {}
active_rooms = {}  # 存储房间信息，包括请求ID

# 数据模型定义
class Row(BaseModel):
    ip: str
    user: str
    password: str
    port: int
    commands: List[str]
    rowId: str

class ConfigData(BaseModel):
    name: str
    data: Dict[str, Any]

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 批量保存结果到数据库
async def save_results_batch(results, db=None):
    """批量保存命令执行结果到数据库"""
    if not results:
        return
        
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
        
    try:
        db.add_all(results)
        db.commit()
        logger.debug(f"Saved {len(results)} results to database")
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving batch results to database: {e}", exc_info=True)
    finally:
        if close_db:
            db.close()

# 执行SSH命令的函数
async def exec_row(row: Row, ws: WebSocket, request_id: str):
    """执行单个服务器上的所有命令"""
    results_batch = []
    conn = None
    
    try:
        # 获取SSH连接（从连接池或新建）
        start_connect = time.time()
        conn = await get_ssh_connection(row.ip, row.user, row.password, row.port)
        connect_time = time.time() - start_connect
        
        logger.info(f"SSH connection established in {connect_time:.2f}s", 
                   extra={"request_id": request_id, "row_id": row.rowId, "ip": row.ip})
        
        # 为每个命令设置信号量，防止单个服务器执行过多命令
        cmd_semaphore = asyncio.Semaphore(50)  # 最多同时执行5个命令
        
        # 定义单个命令执行函数
        async def execute_command(cmd):
            async with cmd_semaphore:
                start_time = time.time()
                try:
                    # 创建进程并设置超时
                    proc = await asyncio.wait_for(
                        conn.create_process(cmd),
                        timeout=300  # 30秒创建进程超时
                    )
                    
                    # 读取输出
                    output = ""
                    exit_status = None
                    
                    try:
                        # 设置读取输出的总超时时间
                        async def read_output():
                            nonlocal output
                            async for line in proc.stdout:
                                output += line
                            output = output.rstrip('\n\r')
                        
                        await asyncio.wait_for(read_output(), timeout=300)  # 5分钟输出读取超时
                                
                        # 等待进程完成并获取退出状态
                        exit_status = await proc.wait()
                    except asyncio.TimeoutError:
                        output += "\n[Command timed out after 300 seconds]"
                        logger.warning(f"Command output reading timed out: {cmd}", 
                                     extra={"request_id": request_id, "row_id": row.rowId, "command": cmd})
                    
                    # 计算执行时间
                    execution_time = time.time() - start_time
                    
                    # 发送命令输出到客户端
                    if hasattr(exit_status, 'exit_status'):
                        # 如果exit_status是SSHCompletedProcess对象
                        json_exit_status = exit_status.exit_status
                    elif hasattr(exit_status, '__dict__'):
                        # 尝试获取字典表示
                        json_exit_status = exit_status.__dict__.get('exit_status', None)
                    else:
                        # 否则直接使用值，可能是None或整数
                        json_exit_status = exit_status

                    await ws.send_json({
                        "rowId": row.rowId,
                        "command": cmd,
                        "output": output,
                        "exitStatus": json_exit_status,
                        # 去掉 executionTime 字段
                    })
                    
                    logger.info(f"Command executed in {execution_time:.2f}s", 
                                extra={
                                    "request_id": request_id,
                                    "row_id": row.rowId,
                                    "command": cmd,
                                    "execution_time": execution_time,
                                    "exit_status": exit_status
                                })
                    
                    # 准备数据库记录（不插入 execution_time 字段）
                    result = ServerCommandResult(
                        ip=row.ip,
                        user=row.user,
                        password="*****",  # 不存储明文密码
                        port=row.port,
                        command=cmd,
                        output=output,
                        exit_status=exit_status,
                        timestamp=datetime.datetime.utcnow()  # 不插入 execution_time 字段
                    )
                    results_batch.append(result)
                    
                    # 每10条记录批量保存一次
                    if len(results_batch) >= 10:
                        await save_results_batch(results_batch)
                        results_batch.clear()
                    
                except asyncio.TimeoutError:
                    execution_time = time.time() - start_time
                    logger.error(f"Command timed out after {execution_time:.2f}s", 
                                extra={"request_id": request_id, "row_id": row.rowId, "command": cmd})
                    
                    await ws.send_json({
                        "rowId": row.rowId,
                        "command": cmd,
                        "error": "Command execution timed out"
                    })
                except Exception as e:
                    execution_time = time.time() - start_time
                    logger.error(f"Error executing command: {e}", 
                               exc_info=True,
                               extra={
                                   "request_id": request_id,
                                   "row_id": row.rowId,
                                   "command": cmd,
                                   "execution_time": execution_time
                               })
                    
                    await ws.send_json({
                        "rowId": row.rowId,
                        "command": cmd,
                        "error": f"{type(e).__name__}: {str(e)}"
                    })
        
        # 并发执行所有命令
        await asyncio.gather(*(execute_command(cmd) for cmd in row.commands))
        
        # 保存剩余结果
        if results_batch:
            await save_results_batch(results_batch)
            
    except Exception as exc:
        logger.error(f"Error in SSH session: {exc}", 
                   exc_info=True,
                   extra={"request_id": request_id, "row_id": row.rowId, "ip": row.ip})
        
        await ws.send_json({
            "rowId": row.rowId,
            "error": f"{type(exc).__name__}: {exc}",
        })
    finally:
        # 注意：不要在这里关闭连接，连接池会处理
        pass

from sqlalchemy import text
from sqlalchemy import inspect
# 在应用启动时检查数据库并添加缺失的列
@app.on_event("startup")
async def startup_event():
    # 启动连接清理任务
    asyncio.create_task(cleanup_connections())
    logger.info("Application started, connection cleanup task running")
    
    # 检查并更新数据库结构
    try:
        # 获取数据库表结构
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('server_command_results')]
        
        # 检查是否缺少 exit_status 列
        if 'exit_status' not in columns:
            logger.info("Missing 'exit_status' column, adding it.")
            with engine.connect() as conn:
                # 使用 text() 函数将 SQL 字符串转化为可执行对象
                conn.execute(text('ALTER TABLE server_command_results ADD COLUMN exit_status INTEGER'))
                logger.info("'exit_status' column added successfully.")
    except Exception as e:
        logger.error(f"Error checking or adding columns: {e}", exc_info=True)

# API端点：执行命令
@app.post("/api/v1/execute")
async def execute(rows: List[Row]):
    """创建房间ID；前端应立即打开WebSocket。"""
    # 生成唯一请求ID和房间ID
    request_id = f"req-{uuid.uuid4().hex[:8]}"
    room = uuid.uuid4().hex
    
    # 验证请求数据
    if not rows:
        logger.warning(f"Empty request received", extra={"request_id": request_id})
        raise HTTPException(status_code=400, detail="No server data provided")
    
    # 存储房间信息
    active_rooms[room] = {
        "rows": rows,
        "request_id": request_id,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "server_count": len(rows),
        "command_count": sum(len(row.commands) for row in rows)
    }
    
    # 设置自动清理任务
    asyncio.create_task(cleanup_room(room, 3600))  # 1小时后清理房间数据
    
    logger.info(f"Execution request received", 
               extra={
                   "request_id": request_id,
                   "room": room,
                   "server_count": len(rows),
                   "command_count": sum(len(row.commands) for row in rows)
               })
    
    return {"room": room, "request_id": request_id}

# 房间数据清理函数
async def cleanup_room(room_id: str, delay: int):
    """延迟清理房间数据"""
    await asyncio.sleep(delay)
    if room_id in active_rooms:
        logger.info(f"Cleaning up expired room", extra={"room": room_id})
        del active_rooms[room_id]

# WebSocket处理
@app.websocket("/ws/{room}")
async def websocket_endpoint(ws: WebSocket, room: str):
    await ws.accept()
    
    # 获取房间数据和请求ID
    room_data = active_rooms.get(room, {})
    request_id = room_data.get("request_id", f"unknown-{uuid.uuid4().hex[:8]}")
    rows = room_data.get("rows", [])
    
    if not rows:
        logger.error(f"No data found for room", extra={"request_id": request_id, "room": room})
        await ws.send_json({"error": "No data available for this room."})
        await ws.close()
        return
    
    # 如果已存在 WebSocket 连接，关闭上一个连接
    if room in websockets:
        logger.warning(f"Existing WebSocket connection detected - closing previous", 
                     extra={"request_id": request_id, "room": room})
        await websockets[room].close()

    websockets[room] = ws

    try:
        logger.info(f"WebSocket connection established", 
                  extra={"request_id": request_id, "room": room})

        # 创建并发控制信号量
        semaphore = asyncio.Semaphore(10)  # 最多10个并发SSH连接
        
        # 使用信号量限制并发
        async def exec_row_with_limit(row):
            async with semaphore:
                await exec_row(row, ws, request_id)
        
        # 并发执行所有行的命令
        await asyncio.gather(*(exec_row_with_limit(row) for row in rows))
        
        # 发送完成消息，通知前端所有命令已执行完毕
        await ws.send_json({"status": "completed"})
        logger.info(f"All commands completed", extra={"request_id": request_id, "room": room})
        
    except Exception as e:
        logger.error(f"Error in WebSocket processing", 
                   exc_info=True,
                   extra={"request_id": request_id, "room": room})
        await ws.send_json({"error": str(e)})
    finally:
        # 清理 WebSocket 连接
        websockets.pop(room, None)
        logger.info(f"WebSocket connection closed", 
                  extra={"request_id": request_id, "room": room})

# 配置管理API
@app.post("/api/v1/configs")
async def save_config(config: ConfigData):
    """保存配置"""
    request_id = f"conf-{uuid.uuid4().hex[:8]}"
    name = config.name
    config_data = json.dumps(config.data)
    
    logger.info(f"Config save request", 
               extra={"request_id": request_id, "config_name": name})
    
    db = SessionLocal()
    try:
        # 检查是否已存在同名配置
        existing = db.query(ServerConfig).filter(ServerConfig.name == name).first()
        if existing:
            existing.config_data = config_data
            existing.updated_at = datetime.datetime.utcnow()
            db.commit()
            logger.info(f"Config updated", 
                      extra={"request_id": request_id, "config_id": existing.id, "config_name": name})
            return {"success": True, "id": existing.id, "name": name, "message": "Config updated"}
        else:
            new_config = ServerConfig(name=name, config_data=config_data)
            db.add(new_config)
            db.commit()
            db.refresh(new_config)
            logger.info(f"New config created", 
                      extra={"request_id": request_id, "config_id": new_config.id, "config_name": name})
            return {"success": True, "id": new_config.id, "name": name, "message": "Config created"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving config", 
                   exc_info=True,
                   extra={"request_id": request_id, "config_name": name})
        return {"success": False, "error": str(e)}
    finally:
        db.close()

@app.get("/api/v1/configs")
async def list_configs():
    """获取配置列表"""
    request_id = f"conf-list-{uuid.uuid4().hex[:8]}"
    logger.info(f"Listing configs", extra={"request_id": request_id})
    
    db = SessionLocal()
    try:
        configs = db.query(ServerConfig).all()
        result = [{"id": c.id, "name": c.name, "updated_at": c.updated_at.isoformat() if c.updated_at else None} for c in configs]
        logger.info(f"Found {len(result)} configs", extra={"request_id": request_id})
        return result
    except Exception as e:
        logger.error(f"Error listing configs", 
                   exc_info=True,
                   extra={"request_id": request_id})
        return {"success": False, "error": str(e)}
    finally:
        db.close()

@app.get("/api/v1/configs/{config_id}")
async def get_config(config_id: int):
    """获取配置详情"""
    request_id = f"conf-get-{uuid.uuid4().hex[:8]}"
    logger.info(f"Getting config details", 
               extra={"request_id": request_id, "config_id": config_id})
    
    db = SessionLocal()
    try:
        config = db.query(ServerConfig).filter(ServerConfig.id == config_id).first()
        if not config:
            logger.warning(f"Config not found", 
                         extra={"request_id": request_id, "config_id": config_id})
            return {"success": False, "error": "Config not found"}
            
        logger.info(f"Config retrieved", 
                  extra={"request_id": request_id, "config_id": config_id, "config_name": config.name})
        return {"success": True, "id": config.id, "name": config.name, "data": json.loads(config.config_data)}
    except Exception as e:
        logger.error(f"Error getting config", 
                   exc_info=True,
                   extra={"request_id": request_id, "config_id": config_id})
        return {"success": False, "error": str(e)}
    finally:
        db.close()

@app.delete("/api/v1/configs/{config_id}")
async def delete_config(config_id: int):
    """删除配置"""
    request_id = f"conf-del-{uuid.uuid4().hex[:8]}"
    logger.info(f"Deleting config", 
               extra={"request_id": request_id, "config_id": config_id})
    
    db = SessionLocal()
    try:
        config = db.query(ServerConfig).filter(ServerConfig.id == config_id).first()
        if not config:
            logger.warning(f"Config not found for deletion", 
                         extra={"request_id": request_id, "config_id": config_id})
            return {"success": False, "error": "Config not found"}
            
        config_name = config.name
        db.delete(config)
        db.commit()
        logger.info(f"Config deleted", 
                  extra={"request_id": request_id, "config_id": config_id, "config_name": config_name})
        return {"success": True, "message": "Config deleted"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting config", 
                   exc_info=True,
                   extra={"request_id": request_id, "config_id": config_id})
        return {"success": False, "error": str(e)}
    finally:
        db.close()