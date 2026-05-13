const isValidIpv4Address = (value) => {
  const ipv4 = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;
  return ipv4.test(value);
};

const isValidIpv6Address = (value) => {
  if (!value.includes(':') || value.includes('[') || value.includes(']')) {
    return false;
  }

  try {
    new URL(`http://[${value}]/`);
    return true;
  } catch {
    return false;
  }
};

const isValidIpAddress = (value) => {
  const normalized = String(value || '').trim();
  if (!normalized) return false;

  return isValidIpv4Address(normalized) || isValidIpv6Address(normalized);
};

const isValidPort = (value) => Number.isInteger(value) && value >= 1 && value <= 65535;

const formatBackendError = (payload) => {
  if (payload?.error?.message) {
    return payload.error.code ? `${payload.error.code}: ${payload.error.message}` : payload.error.message;
  }
  if (payload?.detail) {
    return typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
  }
  return '请求失败，请检查输入后重试。';
};

export { formatBackendError, isValidIpAddress, isValidPort };
