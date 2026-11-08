import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
// 사내망(온프레미스)에서도 동작하도록 글꼴을 번들에 포함 (CDN 미사용)
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
