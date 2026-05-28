import * as env from './core/env.mjs';
import * as registry from './core/registry.mjs';
import * as loader from './loader/module-loader.mjs';

function expose() {
  const g = window;
  g.__StockQProESM__ = g.__StockQProESM__ || {};
  g.__StockQProESM__.env = env;
  g.__StockQProESM__.registry = registry;
  g.__StockQProESM__.loader = loader;
  g.__StockQProESM__.ensurePage = loader.ensurePage;
  g.__StockQProESM__.isEnabled = loader.isEnabled;
  g.__StockQProESM__.getPage = registry.getPage;
}

expose();

