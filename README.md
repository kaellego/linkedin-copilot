# LinkedIn Copilot

Aplicação em Python que pesquisa vagas no LinkedIn e ajuda a processar candidaturas. A interface permite configurar cargo ou palavras-chave, localização, modalidade, tipo de candidatura e cargos a excluir. O robô verifica a relevância da vaga antes de iniciar o fluxo. Candidaturas simplificadas podem ser preenchidas pelo fluxo automatizado; vagas com candidatura externa são abertas para continuação no site da empresa.

> Use a automação de forma responsável e revise cada candidatura antes do envio. As páginas e regras do LinkedIn mudam; o robô pode não reconhecer uma tela ou um campo.

## Requisitos

- Windows 10/11 (a interface principal usa Tkinter e o caminho padrão do Chrome é do Windows).
- Python 3.10 ou superior.
- Google Chrome instalado.
- Uma conta do LinkedIn com sessão iniciada no perfil Chrome usado pelo robô.
- Um serviço de chat compatível com a API OpenAI, se quiser habilitar respostas e análise de relevância por IA.

## Instalação

Abra o PowerShell na pasta do projeto e crie um ambiente virtual:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Crie a configuração local a partir do exemplo:

```powershell
Copy-Item .env.example .env
```

Edite `.env` conforme necessário. Nunca compartilhe nem versione esse arquivo. A configuração atual valida `LINKEDIN_EMAIL`, `LINKEDIN_SENHA` e `CAMINHO_CURRICULO` como obrigatórios. O fluxo principal, porém, conecta-se a um Chrome já autenticado e não faz login automaticamente; entre no LinkedIn manualmente no Chrome iniciado pelo aplicativo.

Para preencher o contexto da IA, copie o modelo e informe o caminho no `.env`:

```powershell
Copy-Item candidate_profile.example.txt candidate_profile.txt
```

Depois edite `candidate_profile.txt` com fatos profissionais verdadeiros e configure `AI_PROFILE_FILE=./candidate_profile.txt`. O arquivo é ignorado pelo Git. Não inclua senhas, tokens, documentos de identificação ou endereço residencial completo.

## Executar

Inicie a interface gráfica principal:

```powershell
python main_tkinter.py
```

Ao iniciar, o aplicativo verifica a porta de depuração `9222`. Se necessário, abre o Chrome com o perfil indicado por `CHROME_DEBUG_PROFILE_PATH`. Faça login nesse Chrome e mantenha a sessão ativa. Se a porta já estiver ocupada, o aplicativo tenta se conectar ao Chrome existente.

Na interface:

1. Informe o cargo ou as palavras-chave e a localização da busca.
2. Escolha a modalidade e o tipo de candidatura.
3. Em **Selecionar termos...**, marque cargos que não devem ser considerados e, se necessário, adicione termos separados por vírgulas. Clique em **Aplicar** para salvar a seleção.
4. Clique em **Iniciar**. Use **Pausar**, **Continuar** ou **Parar** para controlar o processo.

O painel de acompanhamento mostra a vaga atual, a etapa da candidatura, o estado do processo e o progresso da lista; o log abaixo continua exibindo os eventos detalhados. A janela de controle não fica fixa sobre o Chrome, para que seja possível acompanhar visualmente a navegação.

O modo **Todos** considera candidaturas simplificadas e vagas por link. Os modos específicos limitam a busca a candidatura simplificada ou a candidatura por link. Candidaturas externas podem exigir ações manuais no site da empresa; acompanhe a janela aberta.

## Configuração

As variáveis disponíveis estão documentadas em `.env.example`:

| Variável | Finalidade |
| --- | --- |
| `LINKEDIN_EMAIL`, `LINKEDIN_SENHA` | Valores exigidos pela validação atual da configuração local. Não são registrados nos logs. |
| `CAMINHO_CURRICULO` | Caminho do currículo enviado nas candidaturas simplificadas. |
| `PALAVRAS_CHAVE` | Cargo ou termos usados na busca e na avaliação de relevância. Separe alternativas por vírgula. |
| `AI_ENABLED` | Habilita (`true`) ou desabilita (`false`) chamadas à IA. Desabilitada por padrão. |
| `AI_BASE_URL`, `AI_MODEL` | Endereço e nome do modelo no serviço compatível com a API OpenAI. |
| `AI_ALLOW_REMOTE` | Permite endpoint de IA remoto. Por segurança, permanece `false` por padrão. |
| `AI_PROFILE_FILE`, `AI_PROFILE_CONTEXT` | Arquivo e/ou texto com informações profissionais de referência para respostas. |
| `AI_REVIEW_PAUSE_SECONDS` | Pausa entre respostas da IA para permitir revisão. |
| `AI_RESPONSE_LANGUAGE` | Idioma preferido das respostas geradas. |
| `AI_EXCLUDED_ROLE_TERMS` | Seleção inicial de cargos a excluir, separada por vírgulas. A seleção feita na interface é salva em arquivo e carregada nas próximas execuções. |
| `CHROME_EXECUTABLE_PATH`, `CHROME_DEBUG_PROFILE_PATH` | Caminho do Chrome e pasta do perfil usado na depuração. |
| `SELENIUM_WAIT_SECONDS`, `TRANSITION_WAIT_SECONDS` | Limites usados nas esperas do navegador. |
| `JOB_INTERVAL_SECONDS` | Intervalo mínimo, em segundos, entre o início do processamento de vagas consecutivas (padrão: 4). Defina `0` para desativar. |
| `APP_DATA_DIR`, `APP_DEBUG_DIR`, `APP_LOG_DIR` | Pastas locais para dados, depuração e logs. |

No Windows, os dados ficam por padrão em `%LOCALAPPDATA%\LinkedInCopilot` (incluindo sessão, respostas, histórico e termos excluídos). Logs e artefatos de depuração ficam em subpastas dessa área. O projeto tenta remover valores de campos e dados sensíveis dos snapshots de falha, mas trate os artefatos locais como privados.

## IA e respostas

Para usar IA, configure um servidor compatível com `/chat/completions`, ajuste `AI_BASE_URL` e `AI_MODEL`, preencha o perfil profissional e defina `AI_ENABLED=true`. Com `AI_ALLOW_REMOTE=false`, somente endpoints locais são aceitos. Se a IA não puder inferir uma resposta com segurança a partir do perfil, a aplicação pode pedir confirmação manual em vez de inventar dados.

A relevância compara a função principal do cargo com as palavras-chave e aplica os termos de exclusão configurados. Confira a vaga e as respostas antes de enviar; a IA pode interpretar incorretamente descrições ambíguas.

## Diagnóstico

- **Chrome não encontrado:** confira `CHROME_EXECUTABLE_PATH`.
- **Não conectou ao navegador:** feche instâncias que estejam usando a porta `9222` ou configure o perfil de depuração corretamente.
- **Sessão inválida:** faça login manualmente no Chrome controlado pelo aplicativo e tente novamente.
- **IA não responde:** verifique `AI_ENABLED`, o endereço/modelo, a disponibilidade do serviço e o arquivo de perfil. O endpoint remoto precisa de `AI_ALLOW_REMOTE=true`.
- **Tela não reconhecida ou falha no fluxo:** procure o pacote mais recente em `debug` dentro da pasta de dados. Ele inclui HTML sanitizado e `resumo.json` com etapa, URL, erro e sinais da tela.

## Testes

Os testes unitários disponíveis usam Python `unittest` e não precisam abrir o navegador:

```powershell
python -m unittest discover -s tests -v
```

## Estrutura

```text
bot/                 Orquestração do processo
browser/             Criação e conexão do WebDriver
pages/               Busca, login e fluxo das telas de candidatura
services/            Integração com IA
utils/               Privacidade, controle e artefatos de depuração
tests/               Testes unitários
main_tkinter.py      Interface gráfica principal
main.py              Entrada de linha de comando
config.py            Configuração e caminhos da aplicação
```
