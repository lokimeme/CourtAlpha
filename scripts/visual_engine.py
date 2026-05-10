"""
CourtAlpha Visual Intelligence Engine
Generates professional-grade, interactive NBA shot charts.
Uses Plotly for court geometry and coordinate mapping.
"""

import plotly.graph_objects as go
import pandas as pd

class ShotChartEngine:
    def __init__(self):
        self.court_width = 500
        self.half_court_length = 470
        self.hoop_center_y = 0
        self.hoop_center_x = 0
        
    def draw_court_shapes(self, fig):
        """Adds standard NBA court markings to a Plotly figure."""
        
        fig.add_shape(type="circle", x0=-7.5, y0=-7.5, x1=7.5, y1=7.5, line_color="white")
        
        fig.add_shape(type="line", x0=-30, y0=-7.5, x1=30, y1=-7.5, line_color="white")
        
        fig.add_shape(type="rect", x0=-80, y0=-47.5, x1=80, y1=142.5, line_color="white")
        
        fig.add_shape(type="circle", x0=-60, y0=142.5-60, x1=60, y1=142.5+60, line_color="white")
        
        fig.add_shape(type="circle", x0=-40, y0=-0, x1=40, y1=40, line_color="white")
        
        fig.add_shape(type="line", x0=-220, y0=-47.5, x1=-220, y1=92.5, line_color="white")
        fig.add_shape(type="line", x0=220, y0=-47.5, x1=220, y1=92.5, line_color="white")
        
        fig.add_trace(go.Scatter(
            x=[-220, 0, 220],
            y=[92.5, 237.5, 92.5],
            mode='lines',
            line=dict(color='white', width=1, shape='spline'),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        return fig

    def create_shot_chart(self, player_shots, player_name=""):
        """Generates an interactive scatter-based shot chart."""
        
        fig = go.Figure()
        
        if player_shots.empty:
            fig.update_layout(title="No Shot Data Available")
            return fig

        makes = player_shots[player_shots['SHOT_MADE_FLAG'] == 1]
        misses = player_shots[player_shots['SHOT_MADE_FLAG'] == 0]

        fig.add_trace(go.Scatter(
            x=misses['LOC_X'],
            y=misses['LOC_Y'],
            mode='markers',
            name='Missed',
            marker=dict(size=6, color='#FF4B4B', opacity=0.5, symbol='x')
        ))

        fig.add_trace(go.Scatter(
            x=makes['LOC_X'],
            y=makes['LOC_Y'],
            mode='markers',
            name='Made',
            marker=dict(size=7, color='#00CC96', opacity=0.8, symbol='circle')
        ))

        fig = self.draw_court_shapes(fig)

        fig.update_layout(
            title=f"Shot Profile: {player_name}",
            template="plotly_dark",
            showlegend=True,
            xaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-250, 250]),
            yaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-50, 420], scaleanchor="x"),
            width=600,
            height=500,
            margin=dict(l=20, r=20, t=60, b=20),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )

        return fig

    def create_lineup_heatmap(self, density_df, title="Lineup Floor Geometry"):
        """Generates a 2D density heatmap for a 5-man unit."""
        
        fig = go.Figure()
        
        if density_df.empty:
            fig.update_layout(title="No Spatial Data for this Unit")
            return fig

        # Use Histogram2d for better stability with pre-binned data
        fig.add_trace(go.Histogram2d(
            x=density_df['BIN_X'].values,
            y=density_df['BIN_Y'].values,
            z=density_df['SHOT_COUNT'].values,
            histfunc="sum",
            colorscale='YlOrRd',
            reversescale=False,
            opacity=0.8,
            hoverinfo='skip',
            xbins=dict(start=-250, end=250, size=10),
            ybins=dict(start=-50, end=420, size=10)
        ))

        fig = self.draw_court_shapes(fig)

        fig.update_layout(
            title=title,
            template="plotly_dark",
            xaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-250, 250]),
            yaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-50, 420], scaleanchor="x"),
            width=700,
            height=600,
            margin=dict(l=20, r=20, t=60, b=20),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )

        return fig

if __name__ == "__main__":
    engine = ShotChartEngine()
    mock_data = pd.DataFrame({
        'LOC_X': [0, 100, -200, 50, -50],
        'LOC_Y': [10, 50, 250, 300, 150],
        'SHOT_MADE_FLAG': [1, 0, 1, 0, 1]
    })
    fig = engine.create_shot_chart(mock_data, "Test Player")
    print("Shot Chart Engine Ready.")
