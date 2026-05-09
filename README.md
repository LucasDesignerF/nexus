<div align="center">

# 🔮 NEXUS BOT

### *Plataforma SaaS Completa para Discord com Components V2*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.4+-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://mongodb.com)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![QR Code](https://img.shields.io/badge/QR_Code-PIX-00D4AA?style=for-the-badge&logo=qrcode&logoColor=white)](https://www.bcb.gov.br/estabilidadefinanceira/pix)

![Status](https://img.shields.io/badge/Status-Online-2ea44f?style=flat-square)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Support-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/VdFyAr8Gd5)
[![Code Style](https://img.shields.io/badge/code%20style-pep8-000000?style=flat-square)](https://peps.python.org/pep-0008/)

### ✨ *Sistema de Tickets • Email Temporário • Número Virtual • Encurtador de Links • Geração de Senhas • Pagamentos PIX*

<br>

<img src="https://img.shields.io/badge/Components-V2-9C27B0?style=for-the-badge&logo=discord&logoColor=white">
<img src="https://img.shields.io/badge/Arquitetura-SaaS-00ACC1?style=for-the-badge&logo=cloud&logoColor=white">
<img src="https://img.shields.io/badge/Event_Bus-V2.2-FF6D00?style=for-the-badge&logo=eventbrite&logoColor=white">
<img src="https://img.shields.io/badge/Pagamentos-PIX-00D4AA?style=for-the-badge&logo=pix&logoColor=white">

<br>

</div>

---

## 📋 Índice

- [🎯 Visão Geral](#-visão-geral)
- [✨ Funcionalidades](#-funcionalidades)
- [🏗️ Arquitetura](#️-arquitetura)
- [🚀 Instalação](#-instalação)
- [⚙️ Configuração](#️-configuração)
- [📦 Cogs e Módulos](#-cogs-e-módulos)
- [🎨 Discord Components V2](#-discord-components-v2)
- [📊 Banco de Dados](#-banco-de-dados)
- [🔌 API e Integrações](#-api-e-integrações)
- [📝 Comandos](#-comandos)
- [🛡️ Segurança](#️-segurança)
- [🤝 Contribuição](#-contribuição)
- [📄 Licença](#-licença)
- [👥 Créditos](#-créditos)

---

## 🎯 Visão Geral

> **Nexus Bot** é uma plataforma SaaS (Software as a Service) completa para Discord, desenvolvida com a mais recente tecnologia **Components V2** da Discord API. O bot oferece uma suíte de ferramentas profissionais para servidores, incluindo sistema de tickets, emails temporários, números virtuais, encurtador de links, gerador de senhas e **pagamentos via PIX**.

<div align="center">
  
![Banner do Bot](https://imgur.com/uIjtj4Z.png)

</div>

### 🌟 Diferenciais

| Característica | Descrição |
|----------------|-----------|
| **⚡ Components V2** | Interface moderna com Containers, Media Gallery e Sections |
| **🔒 Escalável** | Arquitetura baseada em microserviços com MongoDB + Redis |
| **📊 Event Bus** | Sistema de eventos distribuído para comunicação entre módulos |
| **💾 Cache Inteligente** | Redis para caching e persistência de dados |
| **🎨 UI Moderna** | Design clean com containers coloridos e mídia embutida |
| **🔐 Seguro** | Tokens e dados sensíveis protegidos via .env |
| **💳 Pagamentos PIX** | Geração de QR Code e payload EMV para cobranças |

---

## ✨ Funcionalidades

### 💳 **Sistema de Pagamentos PIX (PRÉMIUM)**
- ✅ Geração de QR Code instantâneo
- ✅ Payload EMV completo (padrão oficial do Banco Central)
- ✅ Código copia e cola
- ✅ Configuração de chave PIX por servidor
- ✅ Validade configurável das cobranças
- ✅ Histórico completo de cobranças
- ✅ Modal interativo para criar cobranças
- ✅ Comando rápido `/pix_quick`
- ✅ Confirmação de pagamento manual
- ✅ Suporte a múltiplos servidores

### 🎫 **Sistema de Tickets (Components V2)**
- ✅ Criação de tickets por categorias customizáveis
- ✅ Sistema de **assumir ticket** com botão dinâmico
- ✅ Transcripts automáticos via **GitHub Gist**
- ✅ Avaliação de atendimento com estrelas (1-5)
- ✅ Painel Staff com ações: banir, advertir, transferir
- ✅ Canais de log e review configuráveis
- ✅ Limite máximo de tickets por usuário
- ✅ Histórico completo de ações

### 📧 **Email Temporário**
- ✅ Criação instantânea de emails descartáveis
- ✅ Integração com **mail.tm API**
- ✅ Domínios dinâmicos e aleatórios
- ✅ Caixa de entrada com visualização de mensagens
- ✅ Sessões persistentes por até 6 horas
- ✅ Cancelamento manual ou automático

### 📞 **Número Temporário**
- ✅ Obtenha números virtuais para receber SMS
- ✅ Suporte a múltiplos países (US, UK, BR, CA, AU, DE, FR, ES, IT)
- ✅ Verificação de mensagens em tempo real
- ✅ Interface idêntica ao sistema de email
- ✅ Validade configurável

### 🔗 **Encurtador de Links**
- ✅ Encurtamento via **TinyURL API**
- ✅ Suporte a validade personalizada (1h a 30 dias)
- ✅ Histórico de links com estatísticas de cliques
- ✅ Modal interativo para inserção de URLs
- ✅ Comando rápido `/encurtar`

### 🔐 **Gerador de Senhas**
- ✅ 5 tipos de senha: Padrão, Segura, Alfanumérica, Numérica, Memorável
- ✅ Histórico local das últimas 10 senhas
- ✅ Avaliação de força da senha
- ✅ Cópia com um clique
- ✅ Sessão de 1 hora para histórico

### 👥 **Sistema de Registro**
- ✅ Painel de registro com botão persistente
- ✅ Modal com nome, apresentação e "como conheceu"
- ✅ Auto-atribuição de cargo verificado/não verificado
- ✅ Definição automática de nickname
- ✅ Estatísticas de registros (total e únicos)
- ✅ Canal de boas-vindas personalizado

### 🛡️ **Moderação**
- ✅ Comandos `/ban`, `/kick`
- ✅ Informações detalhadas de usuário via `/userinfo`
- ✅ Avatar em Media Gallery
- ✅ Interface moderna com Components V2

### 📊 **Eventos de Servidor**
- ✅ Boas-vindas com UI moderna
- ✅ Auto-role para novos membros
- ✅ Logs de entrada e saída
- ✅ Mensagem de boas-vindas por DM
- ✅ Sistema anti-duplicate para eventos

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      DISCORD API                            │
│                   (Components V2 + Gateway)                  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                      NEXUS BOT CORE                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Commands   │  │   Events    │  │  Persistent Views   │  │
│  │   Handler   │  │  Listener   │  │    Registration     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    EVENT BUS (V2.2)                         │
│          • Middleware Pipeline • Async Dispatch             │
│          • Redis Pub/Sub • Distributed Events              │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┬─────────────────┐
        │                 │                 │                 │
┌───────▼───────┐ ┌───────▼───────┐ ┌───────▼───────┐ ┌───────▼───────┐
│    MongoDB    │ │     Redis     │ │   External    │ │   QR Code     │
│   (Primary)   │ │   (Cache +    │ │     APIs      │ │   Generator   │
│   • Dados     │ │    Pub/Sub)   │ │  • mail.tm    │ │   • EMV PIX   │
│   • Configs   │ │   • Sessions  │ │  • TinyURL    │ │   • CRC16     │
│   • Logs      │ │   • Metrics   │ │  • GitHub     │ │   • Payload   │
└───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘
```

### 📁 Estrutura de Diretórios

```
nexus-bot/
├── main.py                 # Entry point principal
├── cogs/
│   ├── admin/
│   │   └── moderation.py   # Moderação e userinfo
│   ├── events/
│   │   └── guild_members.py # Eventos de membros
│   ├── system/
│   │   ├── register.py     # Sistema de registro
│   │   ├── tickets.py      # Sistema de tickets
│   │   └── pix_payments.py # Sistema de pagamentos PIX (NOVO)
│   └── utils/
│       ├── password_gen.py # Gerador de senhas
│       ├── temp_mail.py    # Email temporário
│       ├── temp_number.py  # Número temporário
│       └── url_shortener.py # Encurtador de links
├── pool/
│   ├── connection.py       # MongoDB pool manager
│   ├── redis.py           # Redis pool manager
│   └── event_bus.py       # Event bus distribuído
├── logs/                   # Logs do sistema
├── .env                    # Variáveis de ambiente
└── README.md
```

---

## 🚀 Instalação

### Pré-requisitos

```bash
🐍 Python 3.11+
🍃 MongoDB Atlas (ou local)
📡 Redis Cloud (ou local)
🤖 Discord Bot Token
📱 Biblioteca QR Code
```

### Passo a Passo

```bash
# 1. Clone o repositório
git clone https://github.com/LucasDesignerF/nexus-bot.git
cd nexus-bot

# 2. Crie e ative ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Instale dependências
pip install -r requirements.txt

# 4. Configure variáveis de ambiente
cp .env.example .env
# Edite .env com suas credenciais

# 5. Execute o bot
python main.py
```

### 📦 Dependências Principais

```txt
discord.py>=2.4.0
pymongo>=4.5.0
redis>=5.0.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
qrcode>=7.4.2          # Para geração de QR Code PIX
pillow>=10.0.0         # Para manipulação de imagens
```

---

## ⚙️ Configuração

### Variáveis de Ambiente (.env)

```env
# Discord
DISCORD_TOKEN=seu_token_aqui

# MongoDB
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGO_DB=nexus

# Redis Cloud
REDIS_HOST=redis-xxxxx.c336.samerica-east1-1.gce.cloud.redislabs.com
REDIS_PORT=14831
REDIS_PASSWORD=sua_senha
REDIS_SSL=false

# GitHub (transcripts)
GITHUB_TOKEN=ghp_seu_token
GITHUB_USERNAME=seu_usuario

# Event Bus
EVENT_STREAM=nexus:events
EVENT_GROUP=nexus-workers
EVENT_CONSUMER=worker-1
```

### Configuração do Discord Bot

1. Acesse [Discord Developer Portal](https://discord.com/developers/applications)
2. Crie uma nova aplicação
3. Vá em "Bot" e crie o bot
4. Ative as **Intents**:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent
5. Copie o Token para o `.env`

### Permissões Necessárias

```
- Administrator (recomendado)
- Manage Channels
- Manage Roles
- Kick Members
- Ban Members
- Send Messages
- Embed Links
- Attach Files
- Read Message History
- Use External Emojis
- View Channel
- Manage Webhooks
- Attach Files (para QR Code)
```

---

## 📦 Cogs e Módulos

### 💳 PIXPaymentSystem (`cogs/system/pix_payments.py`) - **NOVO**
Sistema completo de pagamentos via PIX com geração de QR Code e payload EMV.

**Comandos:**
- `/pix` - Abrir painel principal
- `/pix_config` - Configurar chave PIX (Admin)
- `/pix_quick` - Criar cobrança rápida

**Características:**
- Geração de QR Code em tempo real
- Payload EMV padrão Banco Central
- Histórico de cobranças
- Confirmação manual de pagamento

### 🎫 TicketSystem (`cogs/system/tickets.py`)
O coração do bot. Sistema completo de tickets com suporte a múltiplas categorias, transcripts e avaliações.

**Comandos:**
- `/ticket_setup` - Configuração inicial
- `/edit_painel_ticket` - Editar painel
- `/enviar_painel_ticket` - Publicar painel
- `/ticket_stats` - Estatísticas do sistema

### 📧 TempMailSystem (`cogs/utils/temp_mail.py`)
Email descartável via mail.tm API.

**Comandos:**
- `/enviar_painel_email` - Painel principal
- `/meu_email` - Ver email atual
- `/deletar_email` - Remover email

### 📞 TempNumberSystem (`cogs/utils/temp_number.py`)
Números virtuais para SMS.

**Comandos:**
- `/enviar_painel_numero` - Painel principal
- `/meu_numero` - Ver número atual
- `/cancelar_numero` - Remover número

### 🔗 URLShortenerSystem (`cogs/utils/url_shortener.py`)
Encurtador de links via TinyURL.

**Comandos:**
- `/enviar_painel_url` - Painel principal
- `/encurtar <url>` - Encurtar rapidamente
- `/meus_links` - Ver histórico

### 🔐 PasswordGeneratorSystem (`cogs/utils/password_gen.py`)
Gerador de senhas seguras.

**Comandos:**
- `/enviar_painel_senha` - Abrir painel

### 👥 RegisterSystem (`cogs/system/register.py`)
Sistema de registro de membros.

**Comandos:**
- `/reg_config` - Configurar sistema
- `/post_register_panel` - Publicar painel
- `/reg_stats` - Estatísticas

### 🛡️ Moderation (`cogs/admin/moderation.py`)
Comandos de moderação.

**Comandos:**
- `/userinfo` - Informações detalhadas
- `/ban` - Banir membro
- `/kick` - Expulsar membro
- `/test_v2` - Testar Components V2

---

## 🎨 Discord Components V2

O Nexus Bot utiliza a mais recente tecnologia de UI do Discord: **Components V2**.

### Componentes Disponíveis

| Componente | Descrição | Exemplo |
|------------|-----------|---------|
| **Container** | Agrupa componentes com cor de acento | Container roxo para tickets |
| **TextDisplay** | Exibe texto com suporte a Markdown | Mensagens de boas-vindas |
| **MediaGallery** | Galeria de imagens/vídeos | Avatar do usuário |
| **Separator** | Linha divisória visual | Separar seções |
| **Section** | Seção com accessory | Botão + texto lado a lado |
| **ActionRow** | Linha de botões | Botões de ação |

### Exemplo de Uso

```python
# Criando um container
container = discord.ui.Container()
container.accent = 0x5865F2  # Cor roxa do Discord

# Adicionando elementos
container.add_item(discord.ui.TextDisplay(content="# Título"))
container.add_item(discord.ui.Separator())
container.add_item(discord.ui.TextDisplay(content="Conteúdo"))

# Criando section com botão
btn = discord.ui.Button(label="Clique", style=discord.ButtonStyle.primary)
section = discord.ui.Section(accessory=btn)
section.add_item(discord.ui.TextDisplay(content="Descrição"))

# Montando view
view = discord.ui.LayoutView()
view.add_item(container)
view.add_item(section)
```

---

## 📊 Banco de Dados

### MongoDB (Persistência Primária)

**Coleções:**
- `guild_config` - Configurações por servidor
- `ticket_config` - Configurações de tickets
- `ticket_events` - Logs de eventos
- `pix_config` - Configurações de PIX **(NOVO)**

### Redis (Cache + Pub/Sub)

**Estruturas:**
- **Strings**: Configurações e dados temporários
- **Sets**: Tickets ativos por usuário
- **Pub/Sub**: Eventos distribuídos

**Principais Keys:**
```
guild:{id}:config          # Configuração do servidor
ticket:{id}                # Dados do ticket
pix_config:{guild}         # Configuração PIX do servidor (NOVO)
pix_cobranca:{id}          # Dados da cobrança PIX (NOVO)
pix_history:{guild}:{user} # Histórico de cobranças (NOVO)
user_tickets:{guild}:{user} # Tickets do usuário
tempmail:{guild}:{user}    # Sessão de email
tempnumber:{guild}:{user}  # Sessão de número
password_history:{user}    # Histórico de senhas
url_history:{user}         # Histórico de links
nexus:events               # Canal de eventos
```

### Event Bus V2.2

Sistema de eventos distribuído para comunicação entre módulos:

```python
# Emitindo evento
await event_bus.emit("member_join", guild.id, member.id, payload)

# Escutando evento
@event_bus.on("member_join")
async def on_member_join(event):
    print(f"Membro entrou: {event}")
```

---

## 🔌 API e Integrações

### APIs Externas

| Serviço | Endpoint | Uso |
|---------|----------|-----|
| **mail.tm** | `https://api.mail.tm` | Email temporário |
| **TinyURL** | `https://tinyurl.com/api-create.php` | Encurtador de links |
| **GitHub Gist** | `https://api.github.com/gists` | Transcripts |
| **OnlineSMS** | `https://online-sms.org` | Números temporários |
| **QR Code (local)** | `qrcode` + `pillow` | Geração de QR Code PIX |

### Webhooks

```python
# Follow-up de interações
webhook_url = f"https://discord.com/api/v10/webhooks/{app_id}/{token}"
```

---

## 📝 Comandos

### 💳 PIX (NOVO)
| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `/pix` | Abrir painel principal | Todos |
| `/pix_config` | Configurar chave PIX do servidor | Admin |
| `/pix_quick <valor> [descricao]` | Criar cobrança rápida | Todos |

### 🎫 Tickets
| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `/ticket_setup` | Configuração inicial | Admin |
| `/edit_painel_ticket` | Editar painel | Admin |
| `/enviar_painel_ticket` | Publicar painel | Admin |
| `/ticket_set_category` | Definir categoria | Admin |
| `/ticket_set_staff_role` | Definir staff | Admin |
| `/ticket_add_category` | Adicionar categoria | Admin |
| `/ticket_stats` | Estatísticas | Admin |

### 📧 Email Temporário
| Comando | Descrição |
|---------|-----------|
| `/enviar_painel_email` | Abrir painel |
| `/meu_email` | Ver email atual |
| `/deletar_email` | Remover email |

### 📞 Número Temporário
| Comando | Descrição |
|---------|-----------|
| `/enviar_painel_numero` | Abrir painel |
| `/meu_numero` | Ver número atual |
| `/cancelar_numero` | Remover número |

### 🔗 Encurtador
| Comando | Descrição |
|---------|-----------|
| `/enviar_painel_url` | Abrir painel |
| `/encurtar <url>` | Encurtar rapidamente |
| `/meus_links` | Ver histórico |

### 🔐 Senhas
| Comando | Descrição |
|---------|-----------|
| `/enviar_painel_senha` | Abrir painel |

### 👥 Registro
| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `/reg_config` | Configurar sistema | Admin |
| `/post_register_panel` | Publicar painel | Admin |
| `/reg_stats` | Ver estatísticas | Todos |

### 🛡️ Moderação
| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `/userinfo [membro]` | Info do usuário | Todos |
| `/ban <membro> [motivo]` | Banir | Ban Members |
| `/kick <membro> [motivo]` | Expulsar | Kick Members |

---

## 🛡️ Segurança

### Práticas Implementadas

- ✅ **Rate Limiting** via Redis
- ✅ **Validação de Permissões** em todos os comandos
- ✅ **Sanitização de Inputs** em modais
- ✅ **Tokens em .env** (não versionados)
- ✅ **Timeout em Views** (prevenção de abuso)
- ✅ **Anti-Duplicate** em eventos críticos
- ✅ **Logs Detalhados** para auditoria
- ✅ **Validação de Chaves PIX** (formato)

### Proteção de Dados

- Senhas **não são armazenadas** (após exibição)
- Sessões expiram automaticamente
- Dados sensíveis em Redis com TTL
- MongoDB com autenticação
- **Payload PIX** armazenado temporariamente (1 hora)

---

## 🤝 Contribuição

1. **Fork** o projeto
2. **Crie sua branch** (`git checkout -b feature/nova-feature`)
3. **Commit** suas mudanças (`git commit -m 'feat: nova feature'`)
4. **Push** para a branch (`git push origin feature/nova-feature`)
5. Abra um **Pull Request**

### Padrões de Código

- Use **type hints** em todas funções
- Documente com **docstrings**
- Siga PEP 8
- Mantenha **logs** informativos

---

## 📄 Licença

```
MIT License

Copyright (c) 2025 Nexus Platforms

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```

---

## 👥 Créditos

<div align="center">

### Desenvolvido com ❤️ por

| ![LucasDev](https://img.shields.io/badge/Lucas_Dev-000?style=for-the-badge&logo=github&logoColor=white) | ![Nexus Platforms](https://img.shields.io/badge/Nexus_Platforms-5865F2?style=for-the-badge&logo=discord&logoColor=white) |
|-----------|-------------|
| [@LucasDesignerF](https://github.com/LucasDesignerF) | Nexus Bot Developer |

</div>

### Agradecimentos

- **Discord.py** - Biblioteca base
- **MongoDB** - Banco de dados
- **Redis** - Cache e Pub/Sub
- **mail.tm** - API de emails
- **TinyURL** - Encurtador
- **OnlineSMS** - Números virtuais
- **qrcode & pillow** - Geração de QR Code
- **Banco Central do Brasil** - Especificação EMV PIX

---

## 📞 Suporte

<div align="center">

[![Discord](https://img.shields.io/badge/Entre_no_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/VdFyAr8Gd5)
[![GitHub](https://img.shields.io/badge/Ver_no_GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/LucasDesignerF/nexus-bot)
[![Email](https://img.shields.io/badge/Contato_Email-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:lucas@nexusplatforms.com)

---

### 💫 *"O Nexus Bot está em constante evolução. Novas features chegam em breve!"*

</div>

---

<div align="center">

## ⭐ **Dê uma estrela no GitHub se gostou do projeto!** ⭐

**Nexus Bot © 2025 | Nexus Platforms**

---

### 🚀 Última Atualização: Sistema de Pagamentos PIX adicionado!

</div>
