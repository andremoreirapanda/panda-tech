// ============================================================================
// app.js — Registro de rotas (bootstrap)
// ============================================================================

// ---------------------------------------------------------------- Auth
rota("/login", null, (app) => viewLogin(app));
rota("/esqueci-senha", null, (app) => viewEsqueciSenha(app));
rota("/redefinir-senha", null, (app) => viewRedefinirSenha(app));

// ---------------------------------------------------------------- Gestor
rota("/gestor/dashboard", ["gestor"], (app) => viewDashboardGestor(app));
rota("/gestor/pacientes", ["gestor"], (app) => viewListaPacientes(app));
rota("/gestor/paciente/:id", ["gestor"], (app, p) => viewJornadaPaciente(app, p));
rota("/gestor/equipe", ["gestor"], (app) => viewEquipe(app));
rota("/gestor/agenda", ["gestor"], (app) => viewAgenda(app));
rota("/gestor/biblioteca", ["gestor"], (app) => viewBiblioteca(app));
rota("/gestor/mural", ["gestor"], (app) => viewMural(app));
rota("/gestor/mensagens", ["gestor"], (app, p) => viewMensagens(app, p, new URLSearchParams(location.hash.split("?")[1])));
rota("/gestor/financeiro", ["gestor"], (app) => viewFinanceiroGestor(app));
rota("/gestor/indicadores", ["gestor"], (app) => viewIndicadores(app));
rota("/gestor/integracoes", ["gestor"], (app) => viewIntegracoes(app));
rota("/gestor/importar-pacientes", ["gestor"], (app) => viewImportarPacientes(app));
rota("/gestor/modulos", ["gestor"], (app) => viewModulos(app));
rota("/gestor/onboarding", ["gestor"], (app) => viewOnboardingWizard(app));
rota("/gestor/configuracoes", ["gestor"], (app) => viewConfiguracoes(app));
rota("/gestor/perfil", ["gestor"], () => { location.hash = "#/gestor/configuracoes"; });

// ---------------------------------------------------------------- Profissional
rota("/profissional/dashboard", ["profissional"], (app) => viewDashboardProfissional(app));
rota("/profissional/pacientes", ["profissional"], (app) => viewListaPacientes(app));
rota("/profissional/paciente/:id", ["profissional"], (app, p) => viewJornadaPaciente(app, p));
rota("/profissional/agenda", ["profissional"], (app) => viewAgenda(app));
rota("/profissional/biblioteca", ["profissional"], (app) => viewBiblioteca(app));
rota("/profissional/mural", ["profissional"], (app) => viewMural(app));
rota("/profissional/perfil", ["profissional"], (app) => viewPerfilInterno(app));
rota("/profissional/mensagens", ["profissional"], (app, p) => viewMensagens(app, p, new URLSearchParams(location.hash.split("?")[1])));

// ---------------------------------------------------------------- Secretária
// Perfil administrativo opcional (insight do usuário, 31/08/2026): reaproveita
// as mesmas telas de Pacientes/Agenda/Equipe/Mural/Perfil — cada view já se
// adapta ao papel "secretaria" (ver pacientes.js, agenda.js, comunicacao.js,
// financeiro.js). Ela NÃO tem Dashboard, Biblioteca nem Financeiro.
rota("/secretaria/pacientes", ["secretaria"], (app) => viewListaPacientes(app));
rota("/secretaria/paciente/:id", ["secretaria"], (app, p) => viewPacienteSecretaria(app, p));
rota("/secretaria/equipe", ["secretaria"], (app) => viewEquipe(app));
rota("/secretaria/agenda", ["secretaria"], (app) => viewAgenda(app));
rota("/secretaria/mural", ["secretaria"], (app) => viewMural(app));
rota("/secretaria/perfil", ["secretaria"], (app) => viewPerfilInterno(app));

// ---------------------------------------------------------------- Responsável
rota("/responsavel/inicio", ["responsavel"], (app) => viewResponsavelInicio(app));
rota("/responsavel/mensagens", ["responsavel"], (app, p) => viewMensagens(app, p, new URLSearchParams(location.hash.split("?")[1])));
rota("/responsavel/agenda", ["responsavel"], (app) => viewAgenda(app));
rota("/responsavel/mural", ["responsavel"], (app) => viewMural(app));
rota("/responsavel/financeiro", ["responsavel"], (app) => viewFinanceiroResponsavel(app));
rota("/responsavel/perfil", ["responsavel"], (app) => viewPerfilResponsavel(app));

// ---------------------------------------------------------------- Criança (modo lúdico, dentro da sessão do responsável)
rota("/crianca/mundo", ["crianca"], (app) => viewMundoCrianca(app));
rota("/crianca/missao/:id", ["crianca"], (app, p) => viewMissaoCrianca(app, p));
rota("/crianca/medalhas", ["crianca"], (app) => viewMedalhasCrianca(app));

// ---------------------------------------------------------------- Admin do SaaS
rota("/admin/clinicas", ["admin_master"], (app) => viewAdminClinicas(app));
rota("/admin/planos", ["admin_master"], (app) => viewAdminPlanos(app));
rota("/admin/cobrancas-planos", ["admin_master"], (app) => viewAdminCobrancasPlanos(app));
rota("/admin/biblioteca", ["admin_master"], (app) => viewBiblioteca(app));
rota("/admin/monitoramento", ["admin_master"], (app) => viewAdminMonitoramento(app));
rota("/admin/auditoria", ["admin_master"], (app) => viewAdminAuditoria(app));
rota("/admin/integracoes", ["admin_master"], (app) => viewAdminIntegracoes(app));
rota("/admin/perfil", ["admin_master"], (app) => viewAdminPerfil(app));

if (Sessao.logado() && Sessao.usuario?.organizacao) aplicarTemaClinica(Sessao.usuario.organizacao);

despachar();
