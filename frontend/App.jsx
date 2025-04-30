import React, { useRef, useState, useEffect } from 'react';
import { HotTable } from '@handsontable/react';
import 'handsontable/dist/handsontable.full.min.css';
import Handsontable from 'handsontable';
import { ansiToHtml } from './ansi-to-html';
import './App.css';

// 注册数值类型单元格
Handsontable.cellTypes.registerCellType('numeric', Handsontable.cellTypes.numeric);

// 将对象数据转换为二维数组
const convertToArray = (objectData, commands) => {
  return objectData.map(item => [
    item.ip || '',
    item.user || 'root',
    item.password || 'test@1234',
    item.port || 22,
    ...commands.map(cmd => item[cmd] || '')
  ]);
};

// 将二维数组转换为对象数据
const convertToObject = (arrayData, headers) => {
  return arrayData.map(row => {
    const obj = {
      ip: row[0] || '',
      user: row[1] || 'root',
      password: row[2] || 'test@1234',
      port: parseInt(row[3]) || 22
    };
    
    // 添加命令字段
    for (let i = 4; i < headers.length; i++) {
      obj[headers[i]] = row[i] || '';
    }
    
    return obj;
  });
};

// 定义初始数据
const initialData = [
  { ip: '', user: 'root', password: 'test@1234', port: 22 }
];

// 初始命令列
const initialCommands = ['uname -a'];

export default function App() {
  const hotRef = useRef(null);
  const [objectData, setObjectData] = useState(initialData);
  const [commands, setCommands] = useState(initialCommands);
  const [isRunning, setIsRunning] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const isDebugMode = process.env.NODE_ENV === 'development';
  
  // 配置持久化相关状态
  const [configName, setConfigName] = useState("");
  const [savedConfigs, setSavedConfigs] = useState([]);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const fileInputRef = useRef(null);

  // 将对象数据转换为数组数据用于表格
  const data = convertToArray(objectData, commands);

  // 为表头添加双击编辑功能
  const setupHeaderDblClick = () => {
    // 确保表格实例存在
    if (!hotRef.current || !hotRef.current.hotInstance) return;
    
    try {
      const hotInstance = hotRef.current.hotInstance;
      
      // 找到表头行中的所有单元格
      const headerElements = hotInstance.rootElement.querySelectorAll('.ht_clone_top .htCore thead th');
      
      // 为每个表头单元格添加双击事件
      headerElements.forEach((th, index) => {
        // 跳过行标题和基本信息列（IP, User, Password, Port）
        // 表头索引比实际列索引大1（因为第一列是行标题）
        if (index > 0 && index >= 5) { // 第5个是第一个命令列（索引从0开始）
          // 添加视觉提示
          th.style.cursor = 'pointer';
          th.title = '双击编辑命令';
          
          // 使用 ondblclick 而不是 addEventListener，避免多次添加
          th.ondblclick = (e) => {
            // 阻止事件冒泡
            e.preventDefault();
            e.stopPropagation();
            
            // 计算实际列索引 (去除行标题的偏移)
            const colIndex = index - 1;
            
            // 获取当前列标题
            const currentHeader = hotInstance.getColHeader(colIndex);
            
            // 弹出编辑对话框
            const newHeader = prompt("编辑命令:", currentHeader);
            
            // 如果用户输入了新名称且不为空
            if (newHeader && newHeader !== currentHeader && newHeader.trim() !== '') {
              try {
                // 获取所有列标题
                const headers = [...hotInstance.getColHeader()];
                
                // 更新特定列的标题
                headers[colIndex] = newHeader;
                
                // 应用到表格
                hotInstance.updateSettings({
                  colHeaders: headers
                });
                
                // 更新 React 状态
                const newCommands = headers.slice(4);
                setCommands(newCommands);
                
                // 更新对象数据
                const arrayData = hotInstance.getData();
                const updatedObjectData = convertToObject(arrayData, headers);
                setObjectData(updatedObjectData);
              } catch (error) {
                console.error("更新表头时出错:", error);
              }
            }
          };
        }
      });
    } catch (error) {
      console.error("设置表头双击事件时出错:", error);
    }
  };

  // 获取已保存的配置列表
  const fetchConfigs = async () => {
    try {
      setConfigLoading(true);
      const res = await fetch('/api/v1/configs');
      if (res.ok) {
        const configs = await res.json();
        setSavedConfigs(configs);
      } else {
        console.error('Failed to fetch configs:', await res.text());
      }
    } catch (error) {
      console.error('Error fetching configs:', error);
    } finally {
      setConfigLoading(false);
    }
  };

  // 初始加载配置列表
  useEffect(() => {
    fetchConfigs();
  }, []);

  // 表格初始化后设置双击事件
  useEffect(() => {
    // 延迟设置以确保表格完全加载
    const timerId = setTimeout(() => {
      setupHeaderDblClick();
    }, 500);
    
    return () => clearTimeout(timerId);
  }, []);
  
  // 监听表格变化，重新设置双击事件
  useEffect(() => {
    if (!hotRef.current || !hotRef.current.hotInstance) return;
    
    const observer = new MutationObserver(() => {
      // 表格DOM变化时，重新应用双击事件
      setTimeout(() => setupHeaderDblClick(), 0);
    });
    
    try {
      const hotInstance = hotRef.current.hotInstance;
      const tableContainer = hotInstance.rootElement;
      
      if (tableContainer) {
        observer.observe(tableContainer, {
          childList: true,
          subtree: true
        });
      }
    } catch (error) {
      console.error("设置表格观察器时出错:", error);
    }
    
    return () => {
      observer.disconnect();
    };
  }, [hotRef.current, commands]);

  // 保存当前配置
  const saveConfig = async () => {
    if (!configName.trim()) {
      alert("Please enter a configuration name");
      return;
    }
    
    setConfigLoading(true);
    
    // 在保存前获取当前表格的实际数据，确保使用最新状态
    let currentObjectData = objectData;
    let currentCommands = commands;
    
    if (hotRef.current && hotRef.current.hotInstance) {
      const hotInstance = hotRef.current.hotInstance;
      const arrayData = hotInstance.getData();
      const headers = hotInstance.getColHeader();
      
      // 确保我们使用最新的表格数据
      currentObjectData = convertToObject(arrayData, headers);
      currentCommands = headers.slice(4);
    }
    
    try {
      const res = await fetch('/api/v1/configs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: configName,
          data: {
            commands: currentCommands,
            servers: currentObjectData
          }
        })
      });
      
      if (res.ok) {
        const result = await res.json();
        if (result.success) {
          setConfigName("");
          // 获取配置列表但不触发重新渲染表格
          await fetchConfigs();
          setShowConfigModal(false);
          alert(`Configuration "${result.name}" saved successfully`);
        } else {
          alert(`Error: ${result.error || 'Unknown error'}`);
        }
      } else {
        alert(`Error: ${await res.text()}`);
      }
    } catch (error) {
      console.error('Error saving config:', error);
      alert(`Error saving configuration: ${error.message}`);
    } finally {
      setConfigLoading(false);
    }
  };

  // 打开配置保存模态窗口 - 新增函数，确保获取最新表格数据
  const openSaveConfigModal = () => {
    // 首先确保我们捕获当前表格状态，防止modal打开时状态丢失
    if (hotRef.current && hotRef.current.hotInstance) {
      const hotInstance = hotRef.current.hotInstance;
      const arrayData = hotInstance.getData();
      const headers = hotInstance.getColHeader();
      
      // 更新对象数据，确保使用最新状态
      const currentObjectData = convertToObject(arrayData, headers);
      const currentCommands = headers.slice(4);
      
      // 只有在实际有变化时才更新状态，避免不必要的重新渲染
      if (JSON.stringify(currentObjectData) !== JSON.stringify(objectData)) {
        setObjectData(currentObjectData);
      }
      if (JSON.stringify(currentCommands) !== JSON.stringify(commands)) {
        setCommands(currentCommands);
      }
    }
    
    // 然后打开模态窗口
    setShowConfigModal(true);
  };

  // 加载指定配置
  const loadConfig = async (configId) => {
    setConfigLoading(true);
    setShowDropdown(false);
    
    try {
      const res = await fetch(`/api/v1/configs/${configId}`);
      if (res.ok) {
        const result = await res.json();
        
        if (result.success && result.data) {
          if (result.data.commands && Array.isArray(result.data.commands)) {
            setCommands(result.data.commands);
          }
          
          if (result.data.servers && Array.isArray(result.data.servers)) {
            setObjectData(result.data.servers);
          }
          
          alert(`Configuration "${result.name}" loaded successfully`);
        } else {
          alert(`Error: ${result.error || 'Invalid configuration data'}`);
        }
      } else {
        alert(`Error: ${await res.text()}`);
      }
    } catch (error) {
      console.error('Error loading config:', error);
      alert(`Error loading configuration: ${error.message}`);
    } finally {
      setConfigLoading(false);
    }
  };

  // 删除配置
  const deleteConfig = async (configId, configName) => {
    if (!confirm(`Are you sure you want to delete "${configName}"?`)) {
      return;
    }
    
    setConfigLoading(true);
    
    try {
      const res = await fetch(`/api/v1/configs/${configId}`, {
        method: 'DELETE'
      });
      
      if (res.ok) {
        const result = await res.json();
        if (result.success) {
          fetchConfigs();
          alert(`Configuration "${configName}" deleted successfully`);
        } else {
          alert(`Error: ${result.error || 'Unknown error'}`);
        }
      } else {
        alert(`Error: ${await res.text()}`);
      }
    } catch (error) {
      console.error('Error deleting config:', error);
      alert(`Error deleting configuration: ${error.message}`);
    } finally {
      setConfigLoading(false);
    }
  };

  // 导出配置为JSON文件
  const exportConfig = () => {
    setShowDropdown(false);
    
    // 确保我们导出的是当前表格的实际数据
    let currentObjectData = objectData;
    let currentCommands = commands;
    
    if (hotRef.current && hotRef.current.hotInstance) {
      const hotInstance = hotRef.current.hotInstance;
      const arrayData = hotInstance.getData();
      const headers = hotInstance.getColHeader();
      
      currentObjectData = convertToObject(arrayData, headers);
      currentCommands = headers.slice(4);
    }
    
    const configData = {
      commands: currentCommands,
      servers: currentObjectData
    };
    
    const blob = new Blob([JSON.stringify(configData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `server-config-${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // 触发文件选择对话框
  const triggerImport = () => {
    setShowDropdown(false);
    fileInputRef.current.click();
  };

  // 导入配置文件
  const importConfig = (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const config = JSON.parse(e.target.result);
        if (config) {
          if (config.commands && Array.isArray(config.commands)) {
            setCommands(config.commands);
          }
          
          if (config.servers && Array.isArray(config.servers)) {
            setObjectData(config.servers);
          }
          
          alert('Configuration imported successfully');
        } else {
          alert('Invalid configuration file');
        }
      } catch (error) {
        console.error('Error parsing config file:', error);
        alert(`Error parsing configuration file: ${error.message}`);
      }
    };
    reader.readAsText(file);
    
    // 重置文件输入，允许重新选择相同的文件
    event.target.value = null;
  };

  // 执行命令
  const run = async () => {
    if (!hotRef.current) {
      console.error('Table reference not initialized');
      return;
    }
    
    setIsRunning(true);
    setConnectionStatus('connecting');
    setErrorMessage('');

    const hotInstance = hotRef.current.hotInstance;
    const currentArrayData = hotInstance.getData();
    const currentColumns = hotInstance.getColHeader();
    const currentCommands = currentColumns.slice(4);
      
    // 将表格数据转换为后端所需的格式
    const rows = currentArrayData.map((row, idx) => {
      return {
        ip: row[0] || '',
        user: row[1] || 'root',
        password: row[2] || 'test@1234',
        port: parseInt(row[3]) || 22,
        commands: currentCommands,
        rowId: `row-${idx}`
      };
    });

    try {
      const res = await fetch('/api/v1/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rows)
      });

      if (res.ok) {
        const { room } = await res.json();
        console.log("WebSocket room:", room);
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsHost = window.location.hostname; // 自动获取当前主机名
        const wsPort = '8000'; // 或者从环境变量获取
        const wsUrl = `${wsProtocol}://${wsHost}:${wsPort}/ws/${room}`;
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          console.log('WebSocket connection established');
          setConnectionStatus('connected');
        };

        ws.onmessage = (event) => {
          const message = JSON.parse(event.data);
          
          // 处理完成状态消息
          if (message.status === "completed") {
            console.log("All commands completed successfully");
            setIsRunning(false);
            setConnectionStatus(null);
            return;
          }
          
          // 处理错误消息
          if (message.error) {
            setErrorMessage(message.error);
            return;
          }
          
          // 确保消息包含rowId字段
          if (!message.rowId) {
            console.warn("Received message without rowId:", message);
            return;
          }
          
          // 解析行ID以获取行索引
          const rowIdParts = message.rowId.split('-');
          const rowIndex = parseInt(rowIdParts[1]);
          
          if (isNaN(rowIndex) || rowIndex < 0) {
            console.error('Invalid row index from rowId:', message.rowId);
            return;
          }
          
          // 更新对应命令的输出
          if (message.command && message.output) {
            // 找到对应的命令列
            const commandIndex = currentCommands.indexOf(message.command);
            
            if (commandIndex !== -1) {
              const columnIndex = 4 + commandIndex; // IP, User, Password, Port 占用前4列
              
              // 处理ANSI转义序列
              const processedOutput = message.output;
              
              // 创建一个自定义的单元格渲染器
              if (!hotInstance.getCellMeta(rowIndex, columnIndex).renderer) {
                hotInstance.setCellMeta(rowIndex, columnIndex, 'renderer', function(instance, td, row, col, prop, value) {
                  // 默认渲染
                  Handsontable.renderers.TextRenderer.apply(this, arguments);
                  
                  // 如果有值，应用ANSI转换
                  if (value) {
                    // 使用innerHTML设置转换后的HTML
                    td.innerHTML = ansiToHtml(value);
                    
                    // 添加自定义类以应用额外样式
                    td.className += ' ansi-enabled-cell';
                  }
                });
              }
              
              // 设置原始值（不带HTML）到单元格数据
              hotInstance.setDataAtCell(rowIndex, columnIndex, processedOutput);
              
              // 确保单元格仍可选择和复制
              const cellMeta = hotInstance.getCellMeta(rowIndex, columnIndex);
              cellMeta.copyable = true;
              
              // 重新渲染表格
              hotInstance.render();
            }
          } else if (message.output) {
            // 如果没有指定命令，将输出添加到通用输出字段
            const lastColumnIndex = hotInstance.countCols() - 1;
            
            // 处理ANSI转义序列
            const processedOutput = message.output;
            
            // 创建一个自定义的单元格渲染器
            if (!hotInstance.getCellMeta(rowIndex, lastColumnIndex).renderer) {
              hotInstance.setCellMeta(rowIndex, lastColumnIndex, 'renderer', function(instance, td, row, col, prop, value) {
                // 默认渲染
                Handsontable.renderers.TextRenderer.apply(this, arguments);
                
                // 如果有值，应用ANSI转换
                if (value) {
                  // 使用innerHTML设置转换后的HTML
                  td.innerHTML = ansiToHtml(value);
                  
                  // 添加自定义类以应用额外样式
                  td.className += ' ansi-enabled-cell';
                }
              });
            }
            
            // 设置原始值（不带HTML）到单元格数据
            hotInstance.setDataAtCell(rowIndex, lastColumnIndex, processedOutput);
            
            // 确保单元格仍可选择和复制
            const cellMeta = hotInstance.getCellMeta(rowIndex, lastColumnIndex);
            cellMeta.copyable = true;
            
            // 重新渲染表格
            hotInstance.render();
          }
        };
        
        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          setConnectionStatus('error');
          setErrorMessage('WebSocket connection error');
        };

        ws.onclose = () => {
          console.log('WebSocket connection closed');
          setIsRunning(false);
          setConnectionStatus(null);
        };

      } else {
        console.error('Failed to send commands to the backend:', await res.text());
        setConnectionStatus('error');
        setErrorMessage('Failed to send commands to the backend');
        setIsRunning(false);
      }
    } catch (error) {
      console.error('Error executing commands:', error);
      setConnectionStatus('error');
      setErrorMessage(`Error: ${error.message}`);
      setIsRunning(false);
    }
  };

  // 添加新命令列
  const addCommandColumn = (index, commandName) => {
    if (!hotRef.current) return;
    
    const hotInstance = hotRef.current.hotInstance;
    
    // 获取当前数据和列头
    const currentData = hotInstance.getData();
    const currentHeaders = [...hotInstance.getColHeader()];
    
    // 向所有行插入空数据
    const newData = currentData.map(row => {
      const newRow = [...row];
      newRow.splice(index, 0, '');  // 在指定位置插入空字符串
      return newRow;
    });
    
    // 更新表头
    currentHeaders.splice(index, 0, commandName);
    
    // 更新表格
    hotInstance.updateSettings({
      data: newData,
      colHeaders: currentHeaders
    });
    
    // 更新命令列表
    const newCommands = currentHeaders.slice(4);
    setCommands(newCommands);
    
    // 更新对象数据
    const updatedObjectData = convertToObject(newData, currentHeaders);
    setObjectData(updatedObjectData);
  };

  // 删除命令列
  const removeCommandColumn = (index) => {
    if (!hotRef.current) return;
    
    const hotInstance = hotRef.current.hotInstance;
    
    // 获取当前数据和列头
    const currentData = hotInstance.getData();
    const currentHeaders = [...hotInstance.getColHeader()];
    
    // 从所有行中移除该列数据
    const newData = currentData.map(row => {
      const newRow = [...row];
      newRow.splice(index, 1);  // 移除指定位置的列
      return newRow;
    });
    
    // 更新表头
    currentHeaders.splice(index, 1);
    
    // 更新表格
    hotInstance.updateSettings({
      data: newData,
      colHeaders: currentHeaders
    });
    
    // 更新命令列表
    const newCommands = currentHeaders.slice(4);
    setCommands(newCommands);
    
    // 更新对象数据
    const updatedObjectData = convertToObject(newData, currentHeaders);
    setObjectData(updatedObjectData);
  };

  // 重命名表头
  const renameColumn = (index) => {
    if (!hotRef.current || index < 4) return;
    
    const hotInstance = hotRef.current.hotInstance;
    const currentHeader = hotInstance.getColHeader(index);
    
    // 弹出编辑对话框
    const newHeader = prompt("Edit command:", currentHeader);
    if (newHeader && newHeader !== currentHeader && newHeader.trim() !== '') {
      // 更新表头
      const headers = [...hotInstance.getColHeader()];
      headers[index] = newHeader;
      
      // 更新表格设置
      hotInstance.updateSettings({
        colHeaders: headers
      });
      
      // 更新命令列表
      const newCommands = headers.slice(4);
      setCommands(newCommands);
      
      // 更新对象数据
      const arrayData = hotInstance.getData();
      const updatedObjectData = convertToObject(arrayData, headers);
      setObjectData(updatedObjectData);
    }
  };

  // 监听命令列表变化，更新列配置
  useEffect(() => {
    if (hotRef.current && hotRef.current.hotInstance) {
      const hotInstance = hotRef.current.hotInstance;
      const columns = [
        { type: 'text' },   // IP
        { type: 'text' },   // User
        { type: 'text' }, // Password
        { type: 'numeric' }, // Port
        ...commands.map(() => ({ type: 'text', copyable: true, readOnly: false })) // 命令输出列
      ];
      
      hotInstance.updateSettings({ columns });
    }
  }, [commands]);
  
  // 表格配置
  const hotSettings = {
    data: data, // 使用二维数组作为数据源
    colHeaders: ['IP', 'User', 'Password', 'Port', ...commands],
    rowHeaders: true,
    width: "100%",
    height: "auto",
    stretchH: "all",
    manualColumnResize: true,
    manualRowResize: true,
    
    // 启用复制和选择功能
    copyPaste: {
      copyable: true,
      pasteMode: 'overwrite',
      uiContainer: document.body,
      rowsLimit: 10000,
      columnsLimit: 100,
      // 这个配置可以控制复制输出格式
      formattersMap: {
        // 自定义复制格式函数，可以去除引号
        text: value => String(value)
      }
    },
    fragmentSelection: true,
    
    // 确保单元格内容可选
    readOnly: false,
    
    // 定义单元格类型，使命令输出列可读不可写
    columns: [
      { type: 'text' },   // IP
      { type: 'text' },   // User
      { type: 'text' }, // Password
      { type: 'numeric' }, // Port
      ...commands.map(() => ({ type: 'text'})) // 命令输出列
    ],
    
    // 控制哪些列可以重命名
    beforeRenameColumn: (currentColumnName, newColumnName, columnIndex) => {
      // 只允许重命名命令列（索引大于等于4）
      if (columnIndex < 4) {
        // 不允许重命名基本列
        return false;
      }
      
      // 确保命令名不为空
      if (!newColumnName || newColumnName.trim() === '') {
        return false;
      }
      
      // 允许重命名命令列
      return true;
    },
    
    // 处理重命名后的数据更新
    afterRenameColumn: (columnIndex, oldValue, newValue) => {
      if (columnIndex >= 4) {
        // 确保我们访问的是正确的列集合
        const hotInstance = hotRef.current.hotInstance;
        const headers = [...hotInstance.getColHeader()];
        
        // 更新命令列列表
        const newCommands = headers.slice(4);
        setCommands(newCommands);
        
        // 更新对象数据
        const arrayData = hotInstance.getData();
        const updatedObjectData = convertToObject(arrayData, headers);
        setObjectData(updatedObjectData);
      }
    },
    
    // 使用Handsontable内置的右键菜单功能
    contextMenu: {
      items: {
        'row_above': {
          name: 'Insert row above'
        },
        'row_below': {
          name: 'Insert row below'
        },
        'separator1': '---------',
        'col_left': {
          name: 'Insert command column left',
          disabled: function() {
            // 获取选中的单元格
            const selected = this.getSelected();
            if (!selected || !selected.length) return true;
            
            // 获取选中单元格的列索引
            const firstColIndex = selected[0][1];
            
            // 禁止在基本信息列之前插入命令列
            return firstColIndex < 4;
          },
          callback: function() {
            // 获取选中的单元格
            const selected = this.getSelected();
            if (!selected || !selected.length) return;
            
            const [, firstCol] = selected[0];
            
            // 生成临时命令名
            const tempCommandName = `command_${Math.floor(Math.random() * 10000)}`;
            
            // 使用更新后的方法手动实现列插入
            const currentData = this.getData();
            const currentHeaders = [...this.getColHeader()];
            
            // 向所有行插入空数据
            const newData = currentData.map(row => {
              const newRow = [...row];
              newRow.splice(firstCol, 0, '');  // 在指定位置插入空字符串
              return newRow;
            });
            
            // 更新表头
            currentHeaders.splice(firstCol, 0, tempCommandName);
            
            // 更新表格
            this.updateSettings({
              data: newData,
              colHeaders: currentHeaders
            });
            
            // 更新React状态
            const newCommands = currentHeaders.slice(4);
            setCommands(newCommands);
            
            const updatedObjectData = convertToObject(newData, currentHeaders);
            setObjectData(updatedObjectData);
          },
          name: 'Insert command column right',
          disabled: function() {
            const selected = this.getSelected();
            if (!selected || !selected.length) return true;
            
            const firstColIndex = selected[0][1];
            
            // 禁止在基本信息列之前插入命令列
            return firstColIndex < 3; // 允许在Port列后面插入
          },
          callback: function() {
            const selected = this.getSelected();
            if (!selected || !selected.length) return;
            
            const [, firstCol] = selected[0];
            
            // 生成临时命令名
            const tempCommandName = `command_${Math.floor(Math.random() * 10000)}`;
            
            // 使用更新后的方法手动实现列插入
            const currentData = this.getData();
            const currentHeaders = [...this.getColHeader()];
            
            // 向所有行插入空数据
            const newData = currentData.map(row => {
              const newRow = [...row];
              newRow.splice(firstCol + 1, 0, '');  // 在指定位置插入空字符串
              return newRow;
            });
            
            // 更新表头
            currentHeaders.splice(firstCol + 1, 0, tempCommandName);
            
            // 更新表格
            this.updateSettings({
              data: newData,
              colHeaders: currentHeaders
            });
            
            // 更新React状态
            const newCommands = currentHeaders.slice(4);
            setCommands(newCommands);
            
            const updatedObjectData = convertToObject(newData, currentHeaders);
            setObjectData(updatedObjectData);
          }
        },
        'separator2': '---------',
        'remove_row': {
          name: 'Remove row'
        },
        'remove_col': {
          name: 'Remove command column',
          disabled: function() {
            const selected = this.getSelected();
            if (!selected || !selected.length) return true;
            
            const [, firstCol] = selected[0];
            return firstCol < 4; // 禁止删除基本信息列
          },
          callback: function() {
            const selected = this.getSelected();
            if (!selected || !selected.length) return;
            
            const [, firstCol] = selected[0];
            
            // 手动实现列删除
            const currentData = this.getData();
            const currentHeaders = [...this.getColHeader()];
            
            // 从所有行中移除该列数据
            const newData = currentData.map(row => {
              const newRow = [...row];
              newRow.splice(firstCol, 1);  // 移除指定位置的列
              return newRow;
            });
            
            // 更新表头
            currentHeaders.splice(firstCol, 1);
            
            // 更新表格
            this.updateSettings({
              data: newData,
              colHeaders: currentHeaders
            });
            
            // 更新React状态
            const newCommands = currentHeaders.slice(4);
            setCommands(newCommands);
            
            const updatedObjectData = convertToObject(newData, currentHeaders);
            setObjectData(updatedObjectData);
          }
        },
        'separator3': '---------',
        'clear_column': {
          name: 'Clear column'
        },
        'rename_column': {
          name: 'Rename command',
          disabled: function() {
            const selected = this.getSelected();
            if (!selected || !selected.length) return true;
            
            const [, firstCol] = selected[0];
            return firstCol < 4; // 只允许命令列重命名
          },
          callback: function() {
            const selected = this.getSelected();
            if (!selected || !selected.length) return;
            
            const [, firstCol] = selected[0];
            
            if (firstCol >= 4) {
              // 获取当前列标题
              const currentHeader = this.getColHeader()[firstCol];
              
              // 弹出重命名对话框
              const newHeader = prompt("Edit command:", currentHeader);
              
              if (newHeader && newHeader !== currentHeader && newHeader.trim() !== '') {
                // 更新列标题
                const headers = [...this.getColHeader()];
                headers[firstCol] = newHeader;
                this.updateSettings({ colHeaders: headers });
                
                // 更新React状态
                const newCommands = headers.slice(4);
                setCommands(newCommands);
                
                const arrayData = this.getData();
                const updatedObjectData = convertToObject(arrayData, headers);
                setObjectData(updatedObjectData);
              }
            }
          }
        }
      }
    },
    
    // 单元格值改变后的回调
    afterChange: (changes, source) => {
      if (source === 'edit' || source === 'CopyPaste.paste') {
        // 当用户编辑单元格内容时更新对象数据
        const hotInstance = hotRef.current.hotInstance;
        const arrayData = hotInstance.getData();
        const headers = hotInstance.getColHeader();
        
        const updatedObjectData = convertToObject(arrayData, headers);
        setObjectData(updatedObjectData);
      }
    },
    
    // 注册创建/移除列后的回调
    afterCreateCol: (index, amount) => {
      if (index < 4) return; // 忽略基本信息列
      
      // 由于我们在col_left/col_right的callback中已经处理了状态更新
      // 这里不需要重复处理，但保留这个钩子以防需要额外逻辑
    },
    
    afterRemoveCol: (index, amount) => {
      if (index < 4) return; // 忽略基本信息列
      
      // 由于我们在remove_col的callback中已经处理了状态更新
      // 这里不需要重复处理，但保留这个钩子以防需要额外逻辑
    },
    
    // 表格渲染后回调，用于设置双击编辑功能
    afterRender: function() {
      // 延迟执行，确保表格已完全渲染
      setTimeout(() => setupHeaderDblClick(), 0);
    },
    
    // 其他Handsontable设置
    autoWrapRow: true,
    autoWrapCol: true,
    wordWrap: true,
    licenseKey: "non-commercial-and-evaluation"
  };
  
  // 关闭下拉菜单的处理程序
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (showDropdown && !event.target.closest('.dropdown') && !event.target.closest('.dropdown-content')) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [showDropdown]);

  return (
    <div className="container">
      <div className="header">
        <h1 className="title">CyclopsCmd</h1>
        <p className="description">
          Execute and monitor commands across multiple servers. 
          Double-click on command headers to edit them.
          Right-click on the table for more operations.
        </p>
        <p>跨多个服务器执行和监控命令。双击命令标题以对其进行编辑。右键单击表可执行更多作。</p>
      </div>
      
      <div className="button-group">
        <button 
          onClick={run} 
          className={`button primary-button ${isRunning ? 'disabled' : ''}`}
          disabled={isRunning}
        >
          {isRunning ? 'Running Commands' : 'Run Commands'}
          {isRunning && <span className="loading"></span>}
        </button>
        
        <button 
          onClick={openSaveConfigModal} 
          className="button secondary-button"
          disabled={isRunning}
        >
          Save Config
        </button>
        

        <div className="dropdown">
          <button 
            onClick={() => setShowDropdown(!showDropdown)} 
            className="button secondary-button"
            disabled={isRunning || configLoading}
          >
            {configLoading ? 'Loading...' : 'Manage Configs'}
            {configLoading && <span className="loading"></span>}
          </button>
          {showDropdown && (
            <div className="dropdown-content">
              {savedConfigs.length > 0 ? (
                <>
                  <div className="dropdown-header">Saved Configurations</div>
                  {savedConfigs.map(config => (
                    <div key={config.id} className="dropdown-item-container">
                      <a 
                        className="dropdown-item" 
                        onClick={() => loadConfig(config.id)}
                        title={config.name}
                      >
                        {config.name}
                      </a>
                      <button 
                        className="dropdown-delete-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteConfig(config.id, config.name);
                        }}
                        title="Delete configuration"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </>
              ) : (
                <div className="dropdown-empty-state">
                  No saved configurations yet
                </div>
              )}
              
              <div className="dropdown-divider"></div>
              
              <a className="dropdown-action-item" onClick={exportConfig}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Export Configuration
              </a>
              
              <a className="dropdown-action-item" onClick={triggerImport}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                Import Configuration
              </a>
            </div>
          )}
        </div>
        
        {connectionStatus && (
          <div className={`status-indicator status-${connectionStatus}`}>
            <span className="status-dot"></span>
            {connectionStatus === 'connecting' && 'Connecting...'}
            {connectionStatus === 'connected' && 'Connected'}
            {connectionStatus === 'error' && 'Connection Error'}
          </div>
        )}
      </div>
      
      {errorMessage && (
        <div className="error-message">
          {errorMessage}
        </div>
      )}
      
      <div className="table-container">
        <HotTable ref={hotRef} {...hotSettings} />
      </div>
      
      {/* 保存配置模态窗口 */}
      {showConfigModal && (
        <div className="modal">
          <div className="modal-content">
            <h3>Save Configuration</h3>
            <input
              type="text"
              placeholder="Enter configuration name"
              value={configName}
              onChange={(e) => setConfigName(e.target.value)}
              autoFocus
            />
            <div className="modal-buttons">
              <button 
                onClick={() => setShowConfigModal(false)}
                className="button-cancel"
              >
                Cancel
              </button>
              <button 
                onClick={saveConfig}
                className="button-save"
                disabled={!configName.trim() || configLoading}
              >
                {configLoading ? 'Saving...' : 'Save'}
                {configLoading && <span className="loading"></span>}
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* 隐藏的文件输入框，用于导入 */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        style={{ display: 'none' }}
        onChange={importConfig}
      />
    </div>
  );
}
