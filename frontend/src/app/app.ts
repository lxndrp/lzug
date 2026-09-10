import {
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  Injector,
  ViewChild,
  afterNextRender,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Title } from '@angular/platform-browser';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { TuiButton, TuiNotification, TuiRoot } from '@taiga-ui/core';
import { filter } from 'rxjs';

import { AppIconDirective } from './app-icon.directive';
import { appIcons } from './app-icons';
import type { AppView } from './app-view';
import type { AppRouteData } from './app.routes';
import { AuthService } from './auth/auth.service';
import { LifecycleNoticeComponent } from './runtime/lifecycle-notice.component';
import { LifecycleService } from './runtime/lifecycle.service';
import { RuntimeNoticeComponent } from './runtime/runtime-notice.component';
import { ApplicationWorkspaceService } from './shell/application-workspace.service';
import { UiFeedbackService } from './shell/ui-feedback.service';

@Component({
  selector: 'app-root',
  imports: [
    AppIconDirective,
    LifecycleNoticeComponent,
    RouterLink,
    RouterOutlet,
    RuntimeNoticeComponent,
    TuiButton,
    TuiNotification,
    TuiRoot,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly lifecycle = inject(LifecycleService);
  private readonly documentTitle = inject(Title);
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  protected readonly auth = inject(AuthService);
  private readonly workspace = inject(ApplicationWorkspaceService);
  private readonly feedbackService = inject(UiFeedbackService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);
  private readonly router = inject(Router);
  @ViewChild('sidebarClose') private sidebarClose?: ElementRef<HTMLButtonElement>;
  @ViewChild('sidebarToggle') private sidebarToggle?: ElementRef<HTMLButtonElement>;

  protected readonly icons = appIcons;
  protected readonly round = this.workspace.round;
  protected readonly masterData = this.workspace.masterData;
  protected readonly message = this.workspace.message;
  protected readonly loading = this.workspace.loading;
  protected readonly applicationVersion = this.workspace.applicationVersion;
  protected readonly feedback = this.feedbackService.feedback;
  protected readonly activeView = signal<AppView>('dashboard');
  protected readonly pageTitle = signal('Übersicht');
  protected readonly breadcrumb = signal('Aktueller Prüfungskontext');
  protected readonly isContextualView = signal(true);
  protected readonly sidebarVisible = signal(
    typeof window === 'undefined' || window.innerWidth >= 768,
  );
  protected readonly roleSwitchBusy = signal(false);
  protected readonly demoSession = computed(() => {
    const session = this.auth.session();
    return session?.demo_role ? session : null;
  });
  protected readonly activeContext = computed(() => {
    const round = this.round();
    const masterData = this.masterData();
    if (!round || !masterData) return null;

    const halfYear = masterData.examHalfYears.find((item) => item.id === round.exam_half_year_id);
    const committee = masterData.committees.find((item) => item.id === round.committee_id);
    if (!halfYear || !committee) return null;

    return {
      halfYear: `${halfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${halfYear.year}`,
      round: round.name,
      committee: committee.name,
      status: this.roundStatusLabel(round.status),
    };
  });
  protected readonly directAccessDenied = computed(() => !this.canAccessView(this.activeView()));

  constructor() {
    effect(() => {
      this.documentTitle.setTitle(
        this.lifecycle.ready()
          ? `${this.pageTitle()} · lzug`
          : 'Anwendung vorübergehend nicht verfügbar · lzug',
      );
    });
    let previousAuthState: ReturnType<AuthService['state']> | undefined;
    effect(() => {
      const authState = this.auth.state();
      if (previousAuthState === 'anonymous' && authState === 'authenticated') {
        this.refresh();
      }
      previousAuthState = authState;
    });
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.applyRouteData(true));
    this.applyRouteData(false);
    this.checkLifecycle();
  }

  protected checkLifecycle(): void {
    this.lifecycle.check().subscribe((ready) => {
      if (!ready) return;
      this.feedbackService.dismiss();
      this.auth.initialize().subscribe((authenticated) => {
        if (authenticated) this.refresh();
        this.focusPageHeading();
      });
    });
  }

  protected refresh(): void {
    this.workspace.refresh();
  }

  protected closeSidebarOnMobile(): void {
    if (this.isMobileViewport()) this.closeSidebar();
  }

  protected toggleSidebar(): void {
    if (this.sidebarVisible()) this.closeSidebar();
    else this.openSidebar();
  }

  protected openSidebar(): void {
    this.sidebarVisible.set(true);
    afterNextRender(() => this.sidebarClose?.nativeElement.focus(), { injector: this.injector });
  }

  protected closeSidebar(): void {
    if (!this.sidebarVisible()) return;

    this.sidebarToggle?.nativeElement.focus();
    this.sidebarVisible.set(false);
  }

  @HostListener('document:keydown.escape', ['$event'])
  protected closeSidebarWithEscape(event: Event): void {
    if (!this.sidebarVisible() || !this.isMobileViewport()) return;

    event.preventDefault();
    this.closeSidebar();
  }

  private isMobileViewport(): boolean {
    return typeof window !== 'undefined' && window.matchMedia('(max-width: 767.98px)').matches;
  }

  protected roundStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Offen',
      availability_requested: 'Rückmeldungen angefragt',
      availability_closed: 'Rückmeldungen vollständig',
      plan_proposed: 'Planungsvorschlag liegt vor',
      in_progress: 'In Bearbeitung',
      plan_confirmed: 'Plan bestätigt',
    };
    return labels[status] ?? status;
  }

  protected dismissFeedback(): void {
    this.feedbackService.dismiss();
  }

  protected demoRoleLabel(): string {
    const role = this.demoSession()?.demo_role;
    if (role === 'chair') return 'Vorsitz';
    if (role === 'replacement') return 'Angefragter Ersatzprüfer';
    return 'Eingeplanter Prüfer';
  }

  protected demoRoleTask(): string {
    const role = this.demoSession()?.demo_role;
    if (role === 'chair') return 'Koordination und Planrevision';
    if (role === 'replacement') return 'Eigene Ersatzanfrage beantworten';
    return 'Eigenen Ausfall melden';
  }

  protected hasCapability(capability: string): boolean {
    return this.auth.hasCapability(capability);
  }

  protected canAccessView(view: AppView): boolean {
    if (view === 'about') return true;
    if (!this.demoSession()) return view !== 'demo-scenarios';
    if (view === 'demo-scenarios' || view === 'dashboard') return true;
    if (view === 'notifications') return this.hasCapability('notifications:read-own');
    if (view === 'absence-reports') {
      return (
        this.hasCapability('absence:coordinate') ||
        this.hasCapability('absence:write-own') ||
        this.hasCapability('absence:respond-own')
      );
    }
    if (view === 'exam-half-years') return this.hasCapability('exam-half-years:read');
    if (['scheduling-overview', 'planning'].includes(view)) {
      return (
        this.hasCapability('availability:write-own') ||
        this.hasCapability('availability:coordinate') ||
        this.hasCapability('planning-settings:write')
      );
    }
    if (['confirmed-plans', 'exam-day'].includes(view)) {
      return (
        this.hasCapability('confirmed-plan:revise') ||
        this.hasCapability('absence:write-own') ||
        this.hasCapability('attendance:write-own') ||
        this.hasCapability('attendance:coordinate') ||
        this.hasCapability('exam-status:write') ||
        this.hasCapability('exam-result:read')
      );
    }
    return false;
  }

  protected switchDemoRole(): void {
    if (!this.demoSession() || this.roleSwitchBusy()) return;
    void this.router.navigateByUrl('/demo-scenarios');
  }

  private applyRouteData(focusHeading: boolean): void {
    let route = this.router.routerState.root;
    while (route.firstChild) route = route.firstChild;
    const data = route.snapshot.data as Partial<AppRouteData>;
    this.activeView.set(data.view ?? 'dashboard');
    this.pageTitle.set(data.title ?? 'Übersicht');
    this.breadcrumb.set(data.breadcrumb ?? 'Aktueller Prüfungskontext');
    this.isContextualView.set(data.contextual ?? true);
    if (focusHeading) this.focusPageHeading();
  }

  private focusPageHeading(): void {
    afterNextRender(
      () => {
        const heading = this.element.nativeElement.querySelector('h1');
        heading?.setAttribute('tabindex', '-1');
        heading?.focus();
      },
      { injector: this.injector },
    );
  }
}
