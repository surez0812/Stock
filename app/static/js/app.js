// 创建Vue应用
const { createApp, ref, computed, onMounted } = Vue;
const { ElMessage } = ElementPlus;

const app = createApp({
    setup() {
        // 状态定义
        const activeTab = ref('knowledge');
        const htmlContent = ref('<div class="loading">正在加载内容...</div>');
        const markdownContent = ref('');
        const uploadedImage = ref('');
        const uploadedFilename = ref('');
        const imageDescription = ref('');
        const analyzing = ref(false);
        const analysisResult = ref('');
        const selectedProvider = ref('aliyun'); // 默认使用通义千问提供商
        const selectedModel = ref('qwen-vl-max-latest'); // 默认使用最新的视觉模型
        const useShortPrompt = ref(false); // 是否使用精简提示词
        const useOssUpload = ref(true); // 是否使用OSS上传
        const providers = ref([
            { label: 'Mock（模拟）', value: 'mock' },
            { label: 'SiliconFlow (硅流)', value: 'siliconflow' },
            { label: 'Aliyun (通义千问)', value: 'aliyun' }
        ]);
        const availableProviders = ref([]); // 初始为空，等待从服务器获取
        
        // 模型映射
        const providerModels = ref({
            mock: [{value: 'mock-model', label: 'Mock 模型'}],
            siliconflow: [{value: 'Pro/deepseek-ai/DeepSeek-R1', label: 'DeepSeek-R1 (视觉语言)'}],
            aliyun: [
                {value: 'qwen-vl-plus', label: '通义千问 VL Plus (视觉)'},
                {value: 'qwen-plus', label: '通义千问 Plus (文本)'},
                {value: 'qvq-72b-preview', label: '通义千问 72B 预览版 (高级)'},
                {value: 'qwen-vl-max', label: '通义千问 VL Max (高级视觉) 🔥'},
                {value: 'qwen-vl-max-latest', label: '通义千问 VL Max 最新版 (推荐) 🔥'},
                {value: 'qwq-32b', label: '通义千问 32B'},
                {value: 'qwq-plus', label: '通义千问 Plus'}
            ]
        });
        
        // 获取当前提供商可用的模型列表
        const availableModels = computed(() => {
            return providerModels.value[selectedProvider.value] || [];
        });
        
        // 监听提供商变化，自动设置最适合的模型
        const watchProvider = (newProvider) => {
            if (newProvider === 'aliyun') {
                selectedModel.value = 'qwen-vl-max-latest';
            } else if (newProvider === 'siliconflow') {
                selectedModel.value = 'Pro/deepseek-ai/DeepSeek-R1';
            } else {
                selectedModel.value = 'mock-model';
            }
        };
        
        // 格式化分析结果
        const formattedResult = computed(() => {
            if (!analysisResult.value) return '';
            
            let result = analysisResult.value;
            
            // 用HTML标签突出显示建议
            result = result.replace(/买入|购买|加仓/g, '<span class="buy-suggestion">$&</span>');
            result = result.replace(/卖出|抛售|减仓/g, '<span class="sell-suggestion">$&</span>');
            result = result.replace(/观望|持有|等待/g, '<span class="hold-suggestion">$&</span>');
            
            // 添加段落标签
            const paragraphs = result.split('\n\n');
            result = paragraphs.map(p => {
                if (!p.trim()) return '';
                return `<p>${p}</p>`;
            }).join('');
            
            return result;
        });
        
        // 加载Markdown内容
        const loadMarkdown = () => {
            axios.get('/api/markdown')
                .then(response => {
                    if (response.data && response.data.html) {
                        htmlContent.value = response.data.html;
                        markdownContent.value = response.data.markdown;
                    }
                })
                .catch(error => {
                    console.error('加载Markdown失败:', error);
                    htmlContent.value = '<div class="error">加载知识库内容失败，请刷新页面重试</div>';
                    ElMessage.error('加载知识库内容失败，请刷新页面重试');
                });
        };
        
        // 上传前检查
        const beforeUpload = (file) => {
            // 检查文件类型
            const isImage = file.type.startsWith('image/');
            if (!isImage) {
                ElMessage.error('只能上传图片文件!');
                return false;
            }
            
            // 检查文件大小 (小于10MB)
            const isLt10M = file.size / 1024 / 1024 < 10;
            if (!isLt10M) {
                ElMessage.error('图片大小不能超过10MB!');
                return false;
            }
            
            return true;
        };
        
        // 上传成功处理
        const handleUploadSuccess = (response) => {
            if (response && response.path) {
                uploadedImage.value = response.path;
                uploadedFilename.value = response.filename;
                ElMessage.success('图片上传成功');
                
                // 验证图片URL是否可访问
                verifyImageUrl(response.path);
            } else {
                ElMessage.error('上传响应格式错误');
            }
        };
        
        // 验证图片URL
        const verifyImageUrl = (url) => {
            const verificationSection = document.getElementById('verificationSection');
            const verificationStatus = document.getElementById('verificationStatus');
            const verificationDetails = document.getElementById('verificationDetails');
            
            if (!verificationSection || !verificationStatus || !verificationDetails) {
                console.warn('无法找到验证URL的DOM元素');
                return;
            }
            
            verificationSection.style.display = 'block';
            verificationStatus.innerHTML = '<span class="status-badge" style="background-color: #2196f3;">检查中</span>';
            verificationDetails.textContent = `正在验证URL: ${url}`;
            
            const img = new Image();
            
            img.onload = function() {
                verificationStatus.innerHTML = '<span class="status-badge status-success">可访问</span>';
                verificationDetails.textContent = `图片验证成功: ${img.width}x${img.height}`;
            };
            
            img.onerror = function() {
                verificationStatus.innerHTML = '<span class="status-badge status-error">无法访问</span>';
                verificationDetails.textContent = `警告: 图片无法从浏览器直接访问，AI可能也无法访问`;
            };
            
            img.src = url;
            
            // 超时处理
            setTimeout(() => {
                if (!img.complete) {
                    verificationStatus.innerHTML = '<span class="status-badge status-warning">超时</span>';
                    verificationDetails.textContent = `图片加载超时，可能无法被正常访问`;
                }
            }, 5000);
        };
        
        // 上传错误处理
        const handleUploadError = (error) => {
            console.error('上传失败:', error);
            ElMessage.error('图片上传失败，请重试');
        };
        
        // 分析图像
        const analyzeImage = () => {
            if (!uploadedFilename.value) {
                ElMessage.warning('请先上传K线图片');
                return;
            }
            
            analyzing.value = true;
            analysisResult.value = '';
            
            try {
                // 分析参数
                const params = {
                    filename: uploadedFilename.value,
                    description: imageDescription.value,
                    provider: selectedProvider.value,
                    model: selectedModel.value,
                    useShortPrompt: useShortPrompt.value,
                    useOssUpload: useOssUpload.value
                };
                
                console.log('发送分析请求:', params);
                
                axios.post('/api/analyze', params)
                .then(response => {
                    console.log('分析响应:', response.data);
                    if (response.data && response.data.analysis) {
                        analysisResult.value = response.data.analysis;
                        ElMessage.success('分析完成');
                    } else {
                        throw new Error('分析结果为空');
                    }
                })
                .catch(error => {
                    console.error('分析失败:', error);
                    let errorMsg = '分析失败';
                    
                    if (error.response) {
                        console.log('错误响应:', error.response);
                        if (error.response.data && error.response.data.error) {
                            errorMsg += ': ' + error.response.data.error;
                            
                            // 如果错误消息包含"可用提供商"，则更新UI中的提供商列表
                            const errorText = error.response.data.error;
                            const providerMatch = errorText.match(/可用提供商\:\s*\[(.*?)\]/);
                            if (providerMatch && providerMatch[1]) {
                                try {
                                    // 解析返回的提供商列表
                                    const availableProvidersStr = providerMatch[1].replace(/'/g, '"');
                                    const parsed = JSON.parse(`[${availableProvidersStr}]`);
                                    availableProviders.value = parsed;
                                    
                                    // 如果当前选中的提供商不可用，则自动切换到mock
                                    if (!availableProviders.value.includes(selectedProvider.value)) {
                                        selectedProvider.value = 'mock';
                                        ElMessage.warning(`已自动切换到Mock提供商`);
                                    }
                                } catch (e) {
                                    console.error('解析可用提供商失败:', e);
                                }
                            }
                        } else {
                            errorMsg += ': ' + error.response.status + ' ' + error.response.statusText;
                        }
                    } else if (error.message) {
                        errorMsg += ': ' + error.message;
                    }
                    
                    ElMessage.error(errorMsg);
                    
                    // 如果是文件不存在的错误，清除上传状态
                    if (errorMsg.includes('文件不存在')) {
                        uploadedFilename.value = '';
                        uploadedImage.value = '';
                        ElMessage.info('请重新上传图片');
                    }
                })
                .finally(() => {
                    analyzing.value = false;
                });
            } catch (e) {
                console.error('发送请求前出错:', e);
                ElMessage.error('发送请求失败: ' + e.message);
                analyzing.value = false;
            }
        };
        
        // 获取可用的AI提供商
        const fetchAvailableProviders = () => {
            axios.get('/api/status')
                .then(response => {
                    console.log('服务状态:', response.data);
                    if (response.data && response.data.ai_providers) {
                        availableProviders.value = response.data.ai_providers;
                        
                        // 如果当前选择的提供商不在可用列表中，则默认使用mock
                        if (!availableProviders.value.includes(selectedProvider.value) && selectedProvider.value !== 'mock') {
                            selectedProvider.value = 'mock';
                        }
                    }
                })
                .catch(error => {
                    console.error('检查服务状态失败:', error);
                    // 默认使用mock提供商
                    selectedProvider.value = 'mock';
                });
        };
        
        // 获取可用提供商的计算属性
        const filteredProviders = computed(() => {
            return providers.value.filter(p => 
                availableProviders.value.includes(p.value) || p.value === 'mock'
            );
        });
        
        // 页面加载时执行
        onMounted(() => {
            loadMarkdown();
            fetchAvailableProviders();
            
            // 添加提供商变化监听
            watch(selectedProvider, (newValue) => {
                watchProvider(newValue);
            });
        });
        
        // 返回模板需要的所有内容
        return {
            activeTab,
            htmlContent,
            markdownContent,
            uploadedImage,
            uploadedFilename,
            imageDescription,
            analyzing,
            analysisResult,
            selectedProvider,
            selectedModel,
            useShortPrompt,
            useOssUpload,
            providers: filteredProviders,
            availableModels,
            formattedResult,
            beforeUpload,
            handleUploadSuccess,
            handleUploadError,
            analyzeImage
        };
    }
});

// 声明watch函数 (Vue 3特性)
function watch(ref, callback) {
    let oldValue = ref.value;
    Object.defineProperty(ref, 'value', {
        get() {
            return oldValue;
        },
        set(newValue) {
            if (newValue !== oldValue) {
                const prevValue = oldValue;
                oldValue = newValue;
                callback(newValue, prevValue);
            }
        }
    });
}

// 挂载Vue应用
app.use(ElementPlus);
app.mount('#app'); 