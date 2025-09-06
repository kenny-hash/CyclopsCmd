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
    user = Column(String, default='root')
    password = Column(String, default='huawei@1234')
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
jump_server_connections = {}  # 跳板机连接池

async def get_jump_server_connection(jump_host, jump_username, jump_port=22):
    """获取跳板机SSH连接或创建新连接"""
    jump_host = jump_host.replace(" ", "")
    key = f"jump_{jump_host}:{jump_port}:{jump_username}"
    
    # 检查是否有可用的缓存连接
    if key in jump_server_connections:
        try:
            # 尝试执行一个简单的命令来验证连接是否活跃
            conn = jump_server_connections[key]["conn"]
            
            # 实际测试连接是否有效
            try:
                # 使用较短的超时时间来测试连接
                test_proc = await asyncio.wait_for(
                    conn.create_process("echo jump_connection_test"),
                    timeout=10
                )
                test_result = await test_proc.wait()
                
                # 连接有效，更新最后使用时间
                jump_server_connections[key]["last_used"] = time.time()
                logger.debug(f"Reusing jump server SSH connection to {jump_host}:{jump_port}")
                return conn
            except Exception as e:
                # 测试命令失败，连接可能已断开
                logger.warning(f"Jump server SSH connection test failed: {e}")
                raise  # 继续处理异常
                
        except Exception as e:
            # 连接可能已关闭或失效，记录日志并从池中移除
            logger.warning(f"Cached jump server SSH connection to {jump_host}:{jump_port} is invalid, creating new one: {e}")
            try:
                if key in jump_server_connections:
                    try:
                        jump_server_connections[key]["conn"].close()
                    except:
                        pass
                    del jump_server_connections[key]
            except Exception:
                pass
    
    # 创建新的跳板机连接
    try:
        # 使用密钥认证连接跳板机
        conn = await asyncssh.connect(
            jump_host, 
            username=jump_username, 
            port=jump_port, 
            known_hosts=None,
            connect_timeout=30,
            keepalive_interval=60,
            login_timeout=30,
            # 跳板机使用密钥认证，不提供密码
            client_keys='~/.ssh/id_ed25519',  # 使用默认密钥位置 (~/.ssh/id_rsa, ~/.ssh/id_ed25519, etc.)
            passphrase=None
        )
        jump_server_connections[key] = {
            "conn": conn,
            "last_used": time.time()
        }
        logger.info(f"Created new jump server SSH connection to {jump_host}:{jump_port}")
        return conn
    except asyncssh.misc.DisconnectError as e:
        logger.error(f"Jump server SSH disconnection error: {e}", exc_info=True)
        raise
    except asyncssh.misc.ConnectionLost as e:
        logger.error(f"Jump server SSH connection lost: {e}", exc_info=True)
        raise
    except asyncssh.misc.PermissionDenied as e:
        logger.error(f"Jump server SSH permission denied (check SSH key setup): {e}", exc_info=True)
        raise Exception(f"Jump server authentication failed. Please ensure SSH key authentication is configured: {e}")
    except Exception as e:
        logger.error(f"Error creating jump server SSH connection to {jump_host}:{jump_port}: {e}", exc_info=True)
        raise

async def get_ssh_connection_via_jump(host, username, password, port, jump_conn):
    """通过跳板机连接到目标服务器"""
    host = host.replace(" ", "")
    key = f"via_jump_{host}:{port}:{username}"
    
    # 检查是否有可用的缓存连接
    if key in ssh_connections:
        try:
            conn = ssh_connections[key]["conn"]
            
            # 测试连接是否有效
            try:
                test_proc = await asyncio.wait_for(
                    conn.create_process("echo connection_test"),
                    timeout=10
                )
                test_result = await test_proc.wait()
                
                ssh_connections[key]["last_used"] = time.time()
                logger.debug(f"Reusing SSH connection via jump server to {host}:{port}")
                return conn
            except Exception as e:
                logger.warning(f"SSH connection via jump server test failed: {e}")
                raise
                
        except Exception as e:
            logger.warning(f"Cached SSH connection via jump server to {host}:{port} is invalid, creating new one: {e}")
            try:
                if key in ssh_connections:
                    try:
                        ssh_connections[key]["conn"].close()
                    except:
                        pass
                    del ssh_connections[key]
            except Exception:
                pass
    
    # 通过跳板机创建新连接
    try:
        # 使用跳板机连接创建到目标服务器的连接
        conn = await asyncssh.connect(
            host,
            username=username,
            password=password,
            port=port,
            known_hosts=None,
            connect_timeout=30,
            keepalive_interval=60,
            login_timeout=30,
            tunnel=jump_conn  # 使用跳板机连接作为隧道
        )
        ssh_connections[key] = {
            "conn": conn,
            "last_used": time.time()
        }
        logger.info(f"Created new SSH connection via jump server to {host}:{port}")
        return conn
    except Exception as e:
        logger.error(f"Error creating SSH connection via jump server to {host}:{port}: {e}", exc_info=True)
        raise

async def get_ssh_connection(host, username, password, port=22):
    """从连接池获取SSH连接或创建新连接，带有增强的健康检查"""
    host = host.replace(" ","")
    key = f"{host}:{port}:{username}"
    
    # 检查是否有可用的缓存连接
    if key in ssh_connections:
        try:
            # 尝试执行一个简单的命令来验证连接是否活跃
            conn = ssh_connections[key]["conn"]
            
            # 实际测试连接是否有效
            try:
                # 使用较短的超时时间来测试连接
                test_proc = await asyncio.wait_for(
                    conn.create_process("echo connection_test"),
                    timeout=20
                )
                test_result = await test_proc.wait()
                
                # 连接有效，更新最后使用时间
                ssh_connections[key]["last_used"] = time.time()
                logger.debug(f"Reusing SSH connection to {host}:{port}", extra={"connection_key": key})
                return conn
            except Exception as e:
                # 测试命令失败，连接可能已断开
                logger.warning(f"SSH connection test failed: {e}", extra={"connection_key": key})
                raise  # 继续处理异常
                
        except Exception as e:
            # 连接可能已关闭或失效，记录日志并从池中移除
            logger.warning(f"Cached SSH connection to {host}:{port} is invalid, creating new one: {e}")
            try:
                # 尝试安全关闭连接
                if key in ssh_connections:
                    try:
                        ssh_connections[key]["conn"].close()
                    except:
                        pass  # 忽略关闭错误
                    del ssh_connections[key]
            except Exception:
                pass  # 忽略任何异常
    
    # 创建新连接
    try:
        # 增加连接超时和身份验证超时
        conn = await asyncssh.connect(
            host, 
            username=username, 
            password=password, 
            port=port, 
            known_hosts=None,
            connect_timeout=30,  # 30秒连接超时
            keepalive_interval=60,  # 每60秒发送一次keepalive包
            login_timeout=30     # 30秒登录超时
        )
        ssh_connections[key] = {
            "conn": conn,
            "last_used": time.time()
        }
        logger.info(f"Created new SSH connection to {host}:{port}", extra={"connection_key": key})
        return conn
    except asyncssh.misc.DisconnectError as e:
        logger.error(f"SSH disconnection error: {e}", exc_info=True,
                   extra={"host": host, "port": port, "username": username})
        raise
    except asyncssh.misc.ConnectionLost as e:
        logger.error(f"SSH connection lost: {e}", exc_info=True,
                   extra={"host": host, "port": port, "username": username})
        raise
    except Exception as e:
        logger.error(f"Error creating SSH connection to {host}:{port}: {e}", exc_info=True, 
                   extra={"host": host, "port": port, "username": username})
        raise

# 修改连接清理函数以更积极地检查连接健康状态
async def cleanup_connections():
    """清理5分钟未使用的SSH连接并执行健康检查"""
    while True:
        await asyncio.sleep(300)  # 5分钟检查一次
        current_time = time.time()
        cleaned = 0
        checked = 0
        
        # 清理普通SSH连接
        for key, data in list(ssh_connections.items()):
            try:
                # 提取连接信息用于日志
                host_info = key.split(":")
                host = host_info[0] if len(host_info) > 0 else "unknown"
                
                # 连接超过5分钟未使用，直接清理
                if current_time - data["last_used"] > 300:  # 5分钟未使用
                    try:
                        data["conn"].close()
                    except Exception as e:
                        logger.error(f"Error closing SSH connection: {e}", extra={"connection_key": key})
                    
                    del ssh_connections[key]
                    cleaned += 1
                    logger.debug(f"Cleaned idle SSH connection to {host}", extra={"connection_key": key})
                
                # 连接使用超过30分钟，执行健康检查
                elif current_time - data["last_used"] > 1800:  # 30分钟
                    checked += 1
                    try:
                        # 异步测试连接是否健康
                        conn = data["conn"]
                        test_proc = await asyncio.wait_for(
                            conn.create_process("echo health_check"),
                            timeout=5  # 较短的健康检查超时
                        )
                        await test_proc.wait()
                        logger.debug(f"SSH connection to {host} is healthy", extra={"connection_key": key})
                    except Exception as e:
                        # 健康检查失败，关闭并移除连接
                        logger.warning(f"Health check failed for SSH connection to {host}: {e}", 
                                     extra={"connection_key": key})
                        try:
                            data["conn"].close()
                        except:
                            pass
                        
                        del ssh_connections[key]
                        cleaned += 1
            except Exception as e:
                logger.error(f"Error during connection cleanup/health check: {e}", 
                           extra={"connection_key": key})
        
        # 清理跳板机连接
        for key, data in list(jump_server_connections.items()):
            try:
                host_info = key.split(":")
                host = host_info[0].replace("jump_", "") if len(host_info) > 0 else "unknown"
                
                if current_time - data["last_used"] > 300:  # 5分钟未使用
                    try:
                        data["conn"].close()
                    except Exception as e:
                        logger.error(f"Error closing jump server connection: {e}")
                    
                    del jump_server_connections[key]
                    cleaned += 1
                    logger.debug(f"Cleaned idle jump server connection to {host}")
                
                elif current_time - data["last_used"] > 1800:  # 30分钟健康检查
                    checked += 1
                    try:
                        conn = data["conn"]
                        test_proc = await asyncio.wait_for(
                            conn.create_process("echo jump_health_check"),
                            timeout=5
                        )
                        await test_proc.wait()
                        logger.debug(f"Jump server connection to {host} is healthy")
                    except Exception as e:
                        logger.warning(f"Health check failed for jump server connection to {host}: {e}")
                        try:
                            data["conn"].close()
                        except:
                            pass
                        
                        del jump_server_connections[key]
                        cleaned += 1
            except Exception as e:
                logger.error(f"Error during jump server connection cleanup: {e}")
        
        if cleaned > 0 or checked > 0:
            logger.info(f"Connection pool maintenance: cleaned {cleaned} connections, checked {checked} connections")

# WebSocket连接注册表
websockets = {}
active_rooms = {}  # 存储房间信息，包括请求ID

# 数据模型定义
class JumpServerConfig(BaseModel):
    enabled: bool = False
    ip: Optional[str] = None
    user: Optional[str] = None
    port: Optional[int] = 22

class Row(BaseModel):
    ip: str
    user: str
    password: str
    port: int
    commands: List[str]
    rowId: str
    jumpServer: Optional[JumpServerConfig] = None

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

async def exec_row(row: Row, ws: WebSocket, request_id: str):
    """执行单个服务器上的所有命令，支持跳板机连接"""
    results_batch = []
    conn = None
    jump_conn = None
    max_retries = 3  # 最大重试次数
    
    try:
        # 检查是否需要使用跳板机
        use_jump_server = (
            row.jumpServer and 
            row.jumpServer.enabled and 
            row.jumpServer.ip and 
            row.jumpServer.user
        )
        
        start_connect = time.time()
        retry_count = 0
        last_error = None
        
        # 带重试逻辑的连接尝试
        while retry_count < max_retries:
            try:
                if use_jump_server:
                    # 首先连接到跳板机
                    logger.info(f"Connecting via jump server {row.jumpServer.ip}:{row.jumpServer.port}",
                               extra={"request_id": request_id, "row_id": row.rowId})
                    
                    jump_conn = await get_jump_server_connection(
                        row.jumpServer.ip, 
                        row.jumpServer.user, 
                        row.jumpServer.port
                    )
                    
                    # 通过跳板机连接到目标服务器
                    conn = await get_ssh_connection_via_jump(
                        row.ip, row.user, row.password, row.port, jump_conn
                    )
                    
                    logger.info(f"Connected to {row.ip}:{row.port} via jump server",
                               extra={"request_id": request_id, "row_id": row.rowId})
                else:
                    # 直接连接到目标服务器
                    conn = await get_ssh_connection(row.ip, row.user, row.password, row.port)
                
                connect_time = time.time() - start_connect
                logger.info(f"SSH connection established in {connect_time:.2f}s", 
                           extra={"request_id": request_id, "row_id": row.rowId, "ip": row.ip})
                break  # 连接成功，跳出循环
                
            except Exception as e:
                last_error = e
                retry_count += 1
                
                if use_jump_server:
                    logger.warning(f"Jump server connection attempt {retry_count} failed: {e}", 
                                 extra={"request_id": request_id, "row_id": row.rowId, "ip": row.ip})
                else:
                    logger.warning(f"SSH connection attempt {retry_count} failed: {e}", 
                                 extra={"request_id": request_id, "row_id": row.rowId, "ip": row.ip})
                
                if retry_count < max_retries:
                    # 指数退避重试
                    await asyncio.sleep(2 ** retry_count)
                else:
                    # 重试次数用尽，向客户端报告错误
                    error_msg = f"SSH connection failed after {max_retries} attempts: {last_error}"
                    if use_jump_server:
                        error_msg = f"Jump server connection failed after {max_retries} attempts: {last_error}"
                    
                    logger.error(error_msg, extra={"request_id": request_id, "row_id": row.rowId, "ip": row.ip})
                    await ws.send_json({
                        "rowId": row.rowId,
                        "error": error_msg,
                    })
                    return  # 结束函数执行
        
        if conn is None:
            # 如果依然没有连接，返回
            return
            
        # 为每个命令设置信号量，防止单个服务器执行过多命令
        cmd_semaphore = asyncio.Semaphore(5)  # 最多同时执行5个命令，降低了并发度
        
        # 定义单个命令执行函数
        async def execute_command(cmd):
            nonlocal conn, jump_conn  # 引用外部连接变量，以便可以重置
            async with cmd_semaphore:
                start_time = time.time()
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        # 创建进程并设置超时
                        proc = await asyncio.wait_for(
                            conn.create_process(cmd),
                            timeout=60  # 调整为60秒创建进程超时
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
                        })
                        
                        logger.info(f"Command executed in {execution_time:.2f}s", 
                                    extra={
                                        "request_id": request_id,
                                        "row_id": row.rowId,
                                        "command": cmd,
                                        "execution_time": execution_time,
                                        "exit_status": exit_status
                                    })
                        
                        # 准备数据库记录
                        result = ServerCommandResult(
                            ip=row.ip,
                            user=row.user,
                            password="*****",  # 不存储明文密码
                            port=row.port,
                            command=cmd,
                            output=output,
                            exit_status=json_exit_status,
                            timestamp=datetime.datetime.utcnow()
                        )
                        results_batch.append(result)
                        
                        # 每20条记录批量保存一次
                        if len(results_batch) >= 20:
                            await save_results_batch(results_batch)
                            results_batch.clear()
                        
                        # 命令执行成功，跳出重试循环
                        break
                        
                    except (asyncssh.misc.ChannelOpenError, asyncssh.misc.ConnectionLost) as e:
                        # 处理连接关闭错误 - 需要重新连接
                        retry_count += 1
                        execution_time = time.time() - start_time
                        
                        logger.warning(f"SSH connection closed during command execution (attempt {retry_count}): {e}", 
                                     extra={"request_id": request_id, "row_id": row.rowId, "command": cmd})
                        
                        if retry_count < max_retries:
                            # 尝试重新建立连接
                            try:
                                # 将旧连接从连接池中移除
                                if use_jump_server:
                                    key = f"via_jump_{row.ip}:{row.port}:{row.user}"
                                else:
                                    key = f"{row.ip}:{row.port}:{row.user}"
                                
                                if key in ssh_connections:
                                    del ssh_connections[key]
                                
                                # 重新连接
                                if use_jump_server:
                                    # 如果是跳板机连接，可能需要重新连接跳板机
                                    if jump_conn:
                                        try:
                                            # 测试跳板机连接是否还有效
                                            test_proc = await asyncio.wait_for(
                                                jump_conn.create_process("echo test"),
                                                timeout=5
                                            )
                                            await test_proc.wait()
                                        except:
                                            # 跳板机连接也失效了，重新连接
                                            jump_conn = await get_jump_server_connection(
                                                row.jumpServer.ip, 
                                                row.jumpServer.user, 
                                                row.jumpServer.port
                                            )
                                    
                                    conn = await get_ssh_connection_via_jump(
                                        row.ip, row.user, row.password, row.port, jump_conn
                                    )
                                else:
                                    conn = await get_ssh_connection(row.ip, row.user, row.password, row.port)
                                
                                logger.info(f"SSH connection re-established for retry", 
                                          extra={"request_id": request_id, "row_id": row.rowId})
                                
                                # 指数退避策略
                                await asyncio.sleep(2 ** retry_count)
                            except Exception as conn_error:
                                logger.error(f"Failed to re-establish SSH connection: {conn_error}", 
                                           extra={"request_id": request_id, "row_id": row.rowId})
                                raise  # 重新连接失败，向上抛出异常
                        else:
                            # 重试次数用尽
                            logger.error(f"Max retries reached for command execution due to connection issues", 
                                       extra={"request_id": request_id, "row_id": row.rowId, "command": cmd})
                            
                            await ws.send_json({
                                "rowId": row.rowId,
                                "command": cmd,
                                "error": f"SSH connection failed after {max_retries} attempts: {e}"
                            })
                            break
                    
                    except asyncio.TimeoutError:
                        execution_time = time.time() - start_time
                        retry_count += 1
                        
                        logger.warning(f"Command timed out (attempt {retry_count}): {cmd}", 
                                     extra={"request_id": request_id, "row_id": row.rowId})
                        
                        if retry_count < max_retries:
                            # 指数退避策略
                            await asyncio.sleep(2 ** retry_count)
                        else:
                            # 重试次数用尽
                            logger.error(f"Command execution timed out after {execution_time:.2f}s and {max_retries} attempts", 
                                       extra={"request_id": request_id, "row_id": row.rowId, "command": cmd})
                            
                            await ws.send_json({
                                "rowId": row.rowId,
                                "command": cmd,
                                "error": "Command execution timed out after multiple attempts"
                            })
                            break
                    
                    except Exception as e:
                        execution_time = time.time() - start_time
                        retry_count += 1
                        
                        logger.error(f"Error executing command (attempt {retry_count}): {e}", 
                                   exc_info=True,
                                   extra={
                                       "request_id": request_id,
                                       "row_id": row.rowId,
                                       "command": cmd,
                                       "execution_time": execution_time
                                   })
                        
                        if retry_count < max_retries:
                            # 指数退避策略
                            await asyncio.sleep(2 ** retry_count)
                        else:
                            # 重试次数用尽
                            await ws.send_json({
                                "rowId": row.rowId,
                                "command": cmd,
                                "error": f"{type(e).__name__}: {str(e)}"
                            })
                            break
        
        # 使用有限的并发度执行命令，防止过载
        # 这里我们将并发命令数从无限制改为最多20个
        tasks = []
        for cmd in row.commands:
            tasks.append(execute_command(cmd))
            
            # 每20个命令一批，避免创建过多任务
            if len(tasks) >= 20:
                await asyncio.gather(*tasks)
                tasks = []
                
        # 执行剩余的命令
        if tasks:
            await asyncio.gather(*tasks)
        
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
    
    # 验证跳板机配置
    for row in rows:
        if row.jumpServer and row.jumpServer.enabled:
            if not row.jumpServer.ip or not row.jumpServer.ip.strip():
                raise HTTPException(status_code=400, detail="Jump server IP is required when jump server is enabled")
            if not row.jumpServer.user or not row.jumpServer.user.strip():
                raise HTTPException(status_code=400, detail="Jump server username is required when jump server is enabled")
    
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
        semaphore = asyncio.Semaphore(20)  # 最多20个并发SSH连接
        
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